import socket
import os

def rdt_send(filename, target_addr):
    """Hàm ném file đi bằng UDP (Client hoặc Server đều dùng được)"""
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
            
            header = seq_num.to_bytes(4, byteorder='big')
            packet = header + chunk
            
            # Vòng lặp Stop-and-Wait
            # Vòng lặp Stop-and-Wait
            while True:
                udp_sock.sendto(packet, target_addr)
                try:
                    ack_data, _ = udp_sock.recvfrom(1024)
                    if ack_data.decode('utf-8') == f"ACK_{seq_num}":
                        break
                except socket.timeout:
                    pass # Hết giờ (Timeout) thì lặp lại để ném lại mảnh này
                except ConnectionResetError:
                    pass # Bắt và bỏ qua lỗi 10054 của Windows khi Server chưa sẵn sàng
            
            seq_num += 1

    # Báo cờ EOF
    udp_sock.sendto((999999).to_bytes(4, byteorder='big') + b'EOF', target_addr)
    udp_sock.close()
    return True

def rdt_receive(udp_sock, save_filename):
    """Hàm hứng file UDP (Có bộ lọc trùng lặp gói tin)"""
    expected_seq = 0
    
    with open(save_filename, "wb") as f:
        while True:
            data, addr = udp_sock.recvfrom(2048) 
            seq_num = int.from_bytes(data[:4], byteorder='big')
            payload = data[4:] 
            
            if payload == b'EOF':
                udp_sock.sendto(b'ACK_EOF', addr)
                break
                
            # Kiểm duyệt lọc trùng lặp
            if seq_num == expected_seq:
                f.write(payload)
                expected_seq += 1  
            
            # Luôn gửi ACK
            udp_sock.sendto(f"ACK_{seq_num}".encode('utf-8'), addr)