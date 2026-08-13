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
    
    # [QUAN TRỌNG] Chuyển socket sang Non-blocking để vòng lặp không bị đóng băng khi đợi ACK
    udp_sock.setblocking(False) 
    
    WINDOW_SIZE = 5     # Kích thước bộ đệm (Cửa sổ trượt tối đa 5 gói)
    CHUNK_SIZE = 1024
    TIMEOUT = 2.0
    
    base = 0            # Con trỏ chốt sổ: Gói cũ nhất chưa được xác nhận
    next_seq_num = 0    # Con trỏ phát: Gói tiếp theo chuẩn bị gửi
    window_buffer = {}  # Cấu trúc dữ liệu Hash map (Dictionary) lưu các gói đang "bay"
    
    if not os.path.exists(filename):
        return False

    f = open(filename, "rb")
    eof_reached = False
    start_time = time.time()

    # Vòng lặp chạy cho đến khi đọc hết file VÀ mọi gói trong cửa sổ đều đã được ACK an toàn
    while not eof_reached or base < next_seq_num:
        
        # --- BƯỚC 1: BƠM GÓI TIN VÀO CỬA SỔ (FLOW CONTROL) ---
        # Chỉ đọc và gửi thêm nếu khoảng cách giữa con trỏ phát và con trỏ chốt chưa vượt quá Window Size
        while next_seq_num < base + WINDOW_SIZE and not eof_reached:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                eof_reached = True
                break 
            
            packet = make_packet(next_seq_num, 0, FLAG_DATA, chunk)
            window_buffer[next_seq_num] = packet # Lưu bản sao vào buffer để phòng hờ rớt mạng
            
            udp_sock.sendto(packet, target_addr)
            next_seq_num += 1

        # --- BƯỚC 2: HỨNG ACK TỪ RECEIVER ---
        try:
            ack_data, _ = udp_sock.recvfrom(2048)
            ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
            
            # Chỉ dịch cửa sổ lên khi nhận đúng ACK của gói 'base' (Xử lý chặt chẽ theo tuần tự)
            if ack_flag == FLAG_ACK and ack_seq == base:
                del window_buffer[base]  # Giải phóng bộ nhớ gói đã hạ cánh an toàn
                base += 1                # Trượt cửa sổ lên 1 nấc
                start_time = time.time() # Reset lại đồng hồ báo thức
                
        except BlockingIOError:
            pass # Bỏ qua nếu socket chưa có tín hiệu phản hồi (Đặc trưng của Non-blocking)

        # --- BƯỚC 3: XỬ LÝ TIMEOUT (CONGESTION CONTROL / RETRANSMIT) ---
        if time.time() - start_time > TIMEOUT:
            # Thuật toán Go-Back-N: Bắn lại toàn bộ các gói đang nằm trong bộ đệm cửa sổ
            for i in range(base, next_seq_num):
                if i in window_buffer:
                    udp_sock.sendto(window_buffer[i], target_addr)
            start_time = time.time() # Reset lại đồng hồ sau khi bắn lại

    f.close()

    # ==========================================
    # ĐÓNG GÓI EOF KẾT THÚC (Giữ nguyên Stop-and-Wait cho an toàn)
    # ==========================================
    udp_sock.setblocking(True) # Trả về blocking bình thường để gửi chốt hạ
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
                
                # Bóc tách gói tin
                seq_num, ack_num, flags, payload_len, checksum, payload = parse_packet(data)
                
                # 1. Congestion/Error Control: Xác thực tính toàn vẹn (Checksum)
                computed_checksum = zlib.crc32(payload) & 0xffffffff
                if computed_checksum != checksum:
                    continue # Nếu file bị móp méo giữa đường truyền, DROP gói tin (không gửi ACK để bắt bên kia gửi lại)
                
                # 2. Xử lý cờ kết thúc
                if flags == FLAG_EOF:
                    ack_packet = make_packet(seq_num, seq_num, FLAG_ACK, b'')
                    udp_sock.sendto(ack_packet, addr)
                    break
                    
                # 3. Lọc trùng lặp và ghi file
                if seq_num == expected_seq:
                    f.write(payload)
                    expected_seq += 1  
                
                # 4. Bắn ACK xác nhận lại cho Client/Server
                ack_packet = make_packet(seq_num, seq_num, FLAG_ACK, b'')
                udp_sock.sendto(ack_packet, addr)
            
            except Exception:
                pass