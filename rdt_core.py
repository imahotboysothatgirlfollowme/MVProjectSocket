import socket
import os
import struct
import zlib
import time
import select

HEADER_FORMAT = '!IIHHI'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FLAG_DATA = 0x00
FLAG_ACK  = 0x01
FLAG_EOF  = 0x02

def make_packet(seq_num, ack_num, flags, payload):
    payload_len = len(payload)
    checksum = zlib.crc32(payload) & 0xffffffff
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flags, payload_len, checksum)
    return header + payload

def parse_packet(packet):
    header = packet[:HEADER_SIZE]
    payload = packet[HEADER_SIZE:]
    seq_num, ack_num, flags, payload_len, checksum = struct.unpack(HEADER_FORMAT, header)
    return seq_num, ack_num, flags, payload_len, checksum, payload

def rdt_send(filename, target_addr, data_type='I', speed_cb=None, udp_sock=None):
    close_sock_when_done = False
    
    # NẾU CÓ SOCKET TRUYỀN VÀO THÌ DÙNG LẠI, NẾU KHÔNG THÌ TẠO MỚI
    if udp_sock is None:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        close_sock_when_done = True

    udp_sock.setblocking(False) 
    
    cwnd, ssthresh = 1.0, 16.0
    CHUNK_SIZE, TIMEOUT = 1024, 1.0       
    base, next_seq_num = 0, 0    
    window_buffer = {}  
    
    if not os.path.exists(filename): return False
    
    open_kwargs = {}
    if data_type == 'A':
        mode = "r"
        open_kwargs['encoding'] = "utf-8"
        open_kwargs['newline'] = None
    else:
        mode = "rb"
        # Chế độ Binary tuyệt đối không truyền 'encoding' hay 'newline'

    # SỬA LỖI 1: Dùng 'with open' kết hợp kwargs để tự động cấu hình tham số
    with open(filename, mode, **open_kwargs) as f:
        eof_reached = False
        start_time = time.time()
        
        measure_start = time.time()
        bytes_acked_interval = 0

        while not eof_reached or base < next_seq_num:
            current_window_size = int(cwnd)
            while next_seq_num < base + current_window_size and not eof_reached:
                if data_type == 'A':
                    chunk_str = f.read(CHUNK_SIZE // 2)
                    if not chunk_str:
                        eof_reached = True
                        break
                    chunk = chunk_str.replace('\n', '\r\n').encode('utf-8')
                else:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        eof_reached = True
                        break 
                
                packet = make_packet(next_seq_num, 0, FLAG_DATA, chunk)
                window_buffer[next_seq_num] = packet 
                udp_sock.sendto(packet, target_addr)
                
                if base == next_seq_num: start_time = time.time()
                next_seq_num += 1

            # SỬA LỖI 2: Dùng select để socket chờ gói tin tới tối đa 0.01 giây
            # Thao tác này nhường nhịp CPU cho OS, đưa mức ngốn CPU từ 100% xuống ~0%
            ready_to_read, _, _ = select.select([udp_sock], [], [], 0.01)

            if ready_to_read:
                try:
                    while True:
                        ack_data, _ = udp_sock.recvfrom(2048)
                        ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
                        
                        if ack_flag == FLAG_ACK and ack_seq >= base:
                            acked_count = (ack_seq - base + 1)
                            bytes_acked_interval += acked_count * CHUNK_SIZE
                            
                            now = time.time()
                            if now - measure_start >= 0.5:
                                if speed_cb: speed_cb(f"{(bytes_acked_interval / 1024.0) / (now - measure_start):.1f} KB/s")
                                measure_start = now
                                bytes_acked_interval = 0

                            for i in range(base, ack_seq + 1):
                                if i in window_buffer: del window_buffer[i]
                                    
                            base = ack_seq + 1 
                            start_time = time.time() 
                            if cwnd < ssthresh: cwnd += 1.0
                            else: cwnd += (1.0 / int(cwnd))
                except BlockingIOError: 
                    pass 

            # Xử lý Timeout Re-transmission (truyền lại)
            if base < next_seq_num and time.time() - start_time > TIMEOUT:
                ssthresh = max(2.0, cwnd / 2.0)
                cwnd = 1.0                      
                for i in range(base, next_seq_num):
                    if i in window_buffer: udp_sock.sendto(window_buffer[i], target_addr)
                start_time = time.time()

    # Đoạn dọn dẹp kết nối EOF ở lại bên ngoài khối 'with'
    udp_sock.setblocking(True) 
    udp_sock.settimeout(2.0)
    eof_packet = make_packet(next_seq_num, 0, FLAG_EOF, b'EOF')
    
    while True:
        udp_sock.sendto(eof_packet, target_addr)
        try:
            ack_data, _ = udp_sock.recvfrom(2048)
            ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
            if ack_flag == FLAG_ACK and ack_seq == next_seq_num: break
        except (socket.timeout, ConnectionResetError): pass
    
    if speed_cb: speed_cb("0.0 KB/s")
    # SỬA LẠI LOGIC ĐÓNG SOCKET Ở CUỐI CÙNG
    if close_sock_when_done:
        udp_sock.close() # Chỉ đóng nếu rdt_send tự tạo ra nó
    else:
        udp_sock.setblocking(True) # Trả lại trạng thái blocking ban đầu cho socket dùng chung
        
    return True

def rdt_receive(udp_sock, save_filename, data_type='I', speed_cb=None):
    expected_seq = 0
    
    open_kwargs = {}
    if data_type == 'A':
        mode = "w"
        open_kwargs['encoding'] = "utf-8"
        open_kwargs['newline'] = None # Fix lỗi xuống dòng hỗn loạn trên Windows
    else:
        mode = "wb"

    measure_start = time.time()
    bytes_recv_interval = 0

    with open(save_filename, mode, **open_kwargs) as f:
        while True:
            try:
                data, addr = udp_sock.recvfrom(2048) 
                seq_num, ack_num, flags, payload_len, checksum, payload = parse_packet(data)
                
                computed_checksum = zlib.crc32(payload) & 0xffffffff
                if computed_checksum != checksum: continue 
                
                if flags == FLAG_EOF:
                    ack_packet = make_packet(seq_num, seq_num, FLAG_ACK, b'')
                    udp_sock.sendto(ack_packet, addr)
                    break
                    
                if seq_num == expected_seq:
                    if data_type == 'A':
                        text_chunk = payload.decode('utf-8', errors='ignore')
                        f.write(text_chunk.replace('\r\n', '\n'))
                    else:
                        f.write(payload)
                    
                    bytes_recv_interval += len(payload)
                    now = time.time()
                    if now - measure_start >= 0.5:
                        if speed_cb: speed_cb(f"{(bytes_recv_interval / 1024.0) / (now - measure_start):.1f} KB/s")
                        measure_start = now
                        bytes_recv_interval = 0
                        
                    ack_packet = make_packet(expected_seq, expected_seq, FLAG_ACK, b'')
                    udp_sock.sendto(ack_packet, addr)
                    expected_seq += 1  
                else:
                    if expected_seq > 0:
                        ack_packet = make_packet(expected_seq - 1, expected_seq - 1, FLAG_ACK, b'')
                        udp_sock.sendto(ack_packet, addr)
            # Thay thế except Exception: pass bằng đoạn sau:
            except (BlockingIOError, socket.timeout):
                # Bỏ qua an toàn: Gói tin đơn giản là chưa tới
                pass 
            except (struct.error, zlib.error):
                # Bỏ qua an toàn: Gói tin bị hỏng form hoặc sai checksum trong quá trình truyền
                pass
            except ConnectionResetError:
                # NGHIÊM TRỌNG: Đầu kia đã sập hoặc ngắt kết nối đột ngột
                print("[!] Lỗi mạng: Client đã ngắt kết nối đột ngột.")
                break 
            except Exception as e:
                # NHỮNG LỖI LẠ (Lỗi code, v.v.) BẮT BUỘC PHẢI IN RA ĐỂ CÒN SỬA
                print(f"[!] LỖI NGHIÊM TRỌNG TRONG QUÁ TRÌNH NHẬN RDT: {e}")
                break
    if speed_cb: speed_cb("0.0 KB/s")