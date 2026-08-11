import socket

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(("127.0.0.1", 9999))
print("Server UDP đang đợi hứng các mảnh file...")

# THÊM BIẾN NÀY ĐỂ THEO DÕI MẢNH KẾ TIẾP CẦN NHẬN
expected_seq_num = 0  

with open("file_nhan_duoc.txt", "wb") as f:
    while True:
        data, address = server.recvfrom(2048) 
        
        seq_num = int.from_bytes(data[:4], byteorder='big')
        payload = data[4:] 
        
        if payload == b'EOF':
            print("\nĐã nhận được cờ báo kết thúc. Lưu file thành công!")
            server.sendto(b'ACK_EOF', address)
            break
            
        # KIỂM TRA LỌC TRÙNG LẶP (DUPLICATE ELIMINATION)
        if seq_num == expected_seq_num:
            print(f"Đang hứng mảnh số {seq_num}... Ghi vào file.")
            f.write(payload)
            expected_seq_num += 1  # Ghi xong thì tăng số thứ tự mong đợi lên
        else:
            print(f"[!] Bỏ qua mảnh {seq_num} bị trùng lặp do trễ mạng.")
        
        # LUÔN LUÔN GỬI LẠI ACK (Dù là gói mới hay gói trùng)
        ack_packet = f"ACK_{seq_num}".encode('utf-8')
        server.sendto(ack_packet, address)