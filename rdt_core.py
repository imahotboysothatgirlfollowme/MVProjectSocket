import socket
import os
import struct
import zlib
import time

# ==========================================
# CẤU TRÚC CUSTOM UDP HEADER (16 Bytes)
# ==========================================
# Sử dụng module 'struct' để ép kiểu byte chuẩn mạng:
# Format: '! I I H H I'
#   ! : Network byte order (Big-endian)
#   I : Sequence Number   (4 bytes) - Số thứ tự của gói tin
#   I : ACK Number        (4 bytes) - Số thứ tự xác nhận
#   H : Flags             (2 bytes) - Cờ hiệu (DATA, ACK, EOF)
#   H : Payload Length    (2 bytes) - Kích thước thực tế của dữ liệu
#   I : Checksum (CRC32)  (4 bytes) - Mã băm kiểm tra lỗi đường truyền
HEADER_FORMAT = '!IIHHI'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Bảng mã cờ hiệu (Flags)
FLAG_DATA = 0x00
FLAG_ACK  = 0x01
FLAG_EOF  = 0x02

def make_packet(seq_num, ack_num, flags, payload):
    """Hàm đóng gói dữ liệu và gắn Header"""
    payload_len = len(payload)
    # Dùng thuật toán CRC32 để băm payload, đảm bảo data không bị biến dạng lúc truyền
    checksum = zlib.crc32(payload) & 0xffffffff
    
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flags, payload_len, checksum)
    return header + payload

def parse_packet(packet):
    """Hàm bóc tách Header và Payload từ gói nhận được"""
    header = packet[:HEADER_SIZE]
    payload = packet[HEADER_SIZE:]
    
    seq_num, ack_num, flags, payload_len, checksum = struct.unpack(HEADER_FORMAT, header)
    return seq_num, ack_num, flags, payload_len, checksum, payload

def rdt_send(filename, target_addr):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setblocking(False) 
    
    # --- THÊM CONGESTION CONTROL (TIÊU CHÍ EXCELLENT) ---
    cwnd = 1.0          # Congestion Window (Bắt đầu bằng cửa sổ = 1: Slow Start)
    ssthresh = 16.0     # Ngưỡng Slow Start Threshold
    
    CHUNK_SIZE = 1024
    TIMEOUT = 1.0       # Set 1.0s là tối ưu cho mạng LAN/Local
    
    base = 0            # Con trỏ chốt sổ
    next_seq_num = 0    # Con trỏ phát
    window_buffer = {}  # Bộ nhớ đệm (Dictionary)
    
    if not os.path.exists(filename):
        return False

    f = open(filename, "rb")
    eof_reached = False
    start_time = time.time()

    while not eof_reached or base < next_seq_num:
        
        current_window_size = int(cwnd) # Lấy phần nguyên của cửa sổ hiện tại
        
        # --- BƯỚC 1: BƠM GÓI TIN THEO CỬA SỔ ĐỘNG ---
        while next_seq_num < base + current_window_size and not eof_reached:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                eof_reached = True
                break 
            
            packet = make_packet(next_seq_num, 0, FLAG_DATA, chunk)
            window_buffer[next_seq_num] = packet 
            udp_sock.sendto(packet, target_addr)
            
            # Chỉ khởi động lại đồng hồ khi gửi gói đầu tiên trong cửa sổ
            if base == next_seq_num: 
                start_time = time.time()
                
            next_seq_num += 1

        # --- BƯỚC 2: HỨNG ACK (CUMULATIVE ACK) ---
        try:
            # Dùng vòng lặp while để vét sạch toàn bộ ACK đang kẹt trong buffer hệ điều hành
            while True:
                ack_data, _ = udp_sock.recvfrom(2048)
                ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
                
                # Nếu là ACK hợp lệ và nằm trong hoặc cao hơn mốc base hiện tại
                if ack_flag == FLAG_ACK and ack_seq >= base:
                    
                    # Giải phóng toàn bộ các gói từ base đến ack_seq ra khỏi RAM
                    for i in range(base, ack_seq + 1):
                        if i in window_buffer:
                            del window_buffer[i]
                            
                    base = ack_seq + 1 # Trượt con trỏ cái "vèo" qua tất cả
                    start_time = time.time() # Reset đồng hồ
                    
                    # [TĂNG TỐC ĐỘ TRUYỀN TẢI THEO MẠNG]
                    if cwnd < ssthresh:
                        cwnd += 1 # Slow Start: Tăng tốc cực nhanh theo hàm mũ
                    else:
                        cwnd += 1.0 / int(cwnd) # Congestion Avoidance: Tăng chậm lại tránh nghẽn
                        
        except BlockingIOError:
            pass # Socket non-blocking sẽ ném lỗi này nếu không có dữ liệu, ta bỏ qua

        # --- BƯỚC 3: XỬ LÝ TIMEOUT & RETRANSMIT (GBN) ---
        # Chỉ check timeout nếu vẫn còn gói đang bay (base < next_seq_num)
        if base < next_seq_num and time.time() - start_time > TIMEOUT:
            
            # [PHẠT MẠNG TẮC NGHẼN] Rớt gói -> Giảm cửa sổ truyền
            ssthresh = max(2.0, cwnd / 2.0) # Lưu lại mốc an toàn
            cwnd = 1.0 # Ép mạng khởi động lại từ đầu để tránh dội bom UDP
            
            # Bắn lại toàn bộ các gói đang nằm trong bộ đệm cửa sổ
            for i in range(base, next_seq_num):
                if i in window_buffer:
                    udp_sock.sendto(window_buffer[i], target_addr)
            start_time = time.time()

    f.close()

    # ==========================================
    # GỬI GÓI EOF (Giữ nguyên logic của bạn - Stop & Wait an toàn)
    # ==========================================
    udp_sock.setblocking(True) 
    udp_sock.settimeout(2.0)
    eof_packet = make_packet(next_seq_num, 0, FLAG_EOF, b'EOF')
    
    while True:
        udp_sock.sendto(eof_packet, target_addr)
        try:
            ack_data, _ = udp_sock.recvfrom(2048)
            ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
            if ack_flag == FLAG_ACK and ack_seq == next_seq_num:
                break
        except (socket.timeout, ConnectionResetError):
            pass

    udp_sock.close()
    return True

def rdt_receive(udp_sock, save_filename):
    expected_seq = 0
    
    with open(save_filename, "wb") as f:
        while True:
            try:
                data, addr = udp_sock.recvfrom(2048) 
                seq_num, ack_num, flags, payload_len, checksum, payload = parse_packet(data)
                
                # 1. Congestion/Error Control: Xác thực toàn vẹn
                computed_checksum = zlib.crc32(payload) & 0xffffffff
                if computed_checksum != checksum:
                    continue # Bỏ qua gói lỗi (không làm gì cả để ép Sender timeout)
                
                # 2. Xử lý cờ kết thúc
                if flags == FLAG_EOF:
                    ack_packet = make_packet(seq_num, seq_num, FLAG_ACK, b'')
                    udp_sock.sendto(ack_packet, addr)
                    break
                    
                # 3. LOGIC GBN RECEIVER CHUẨN
                if seq_num == expected_seq:
                    # Gói đến ĐÚNG thứ tự -> Ghi file và gửi ACK cho chính nó
                    f.write(payload)
                    ack_packet = make_packet(expected_seq, expected_seq, FLAG_ACK, b'')
                    udp_sock.sendto(ack_packet, addr)
                    expected_seq += 1  
                else:
                    # Gói đến SAI thứ tự -> Vứt đi và gửi lại ACK của gói đúng gần nhất
                    if expected_seq > 0:
                        ack_packet = make_packet(expected_seq - 1, expected_seq - 1, FLAG_ACK, b'')
                        udp_sock.sendto(ack_packet, addr)
            
            except Exception:
                pass