import socket
import os
import struct
import zlib

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

# ==========================================
# CÁC HÀM TRUYỀN TẢI RDT (Stop-and-Wait)
# ==========================================
def rdt_send(filename, target_addr):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.settimeout(2.0)
    
    seq_num = 0
    CHUNK_SIZE = 1024
    
    if not os.path.exists(filename):
        return False

    with open(filename, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break 
            
            # Khởi tạo gói tin mang dữ liệu (Cờ FLAG_DATA)
            packet = make_packet(seq_num, 0, FLAG_DATA, chunk)
            
            # Vòng lặp truyền - chờ ACK
            while True:
                udp_sock.sendto(packet, target_addr)
                try:
                    ack_data, _ = udp_sock.recvfrom(2048)
                    
                    # Bóc tách gói ACK vừa nhận
                    ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
                    
                    # Đối chiếu: Đúng là cờ ACK và khớp số Sequence
                    if ack_flag == FLAG_ACK and ack_seq == seq_num:
                        break
                except socket.timeout:
                    pass # Hết 2 giây không thấy ACK thì vòng lặp quay lại ném tiếp (Timeout Recovery)
                except ConnectionResetError:
                    pass 
            
            seq_num += 1

    # Khi hết file, ném một gói tin rỗng mang cờ FLAG_EOF để báo hiệu
    eof_packet = make_packet(seq_num, 0, FLAG_EOF, b'EOF')
    while True:
        udp_sock.sendto(eof_packet, target_addr)
        try:
            ack_data, _ = udp_sock.recvfrom(2048)
            ack_seq, _, ack_flag, _, _, _ = parse_packet(ack_data)
            if ack_flag == FLAG_ACK and ack_seq == seq_num:
                break
        except socket.timeout:
            pass
        except ConnectionResetError:
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