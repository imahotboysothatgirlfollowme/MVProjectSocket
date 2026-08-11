import socket

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(("127.0.0.1", 9999))
print("Server UDP đang đợi hứng các mảnh file...")

with open("file_nhan_duoc.txt", "wb") as f:
    while True:
        data, address = server.recvfrom(2048) 
        
        # Bóc nhãn lấy số thứ tự
        seq_num = int.from_bytes(data[:4], byteorder='big')
        payload = data[4:] 
        
        # Bắt cờ kết thúc
        if payload == b'EOF':
            print("\nĐã nhận được cờ báo kết thúc. Lưu file thành công!")
            server.sendto(b'ACK_EOF', address)
            break
            
        print(f"Đang hứng mảnh số {seq_num}... Gửi lại ACK_{seq_num}")
        f.write(payload)
        
        # ĐÂY LÀ "CÁI MIỆNG" CỦA SERVER: TẠO VÀ GỬI ACK NGƯỢC LẠI
        ack_packet = f"ACK_{seq_num}".encode('utf-8')
        server.sendto(ack_packet, address)