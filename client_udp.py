import socket

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# BẬT TÍNH NĂNG TIMEOUT: Đợi tối đa 2 giây cho mỗi lần nghe phản hồi
client.settimeout(2.0) 
server_address = ("127.0.0.1", 9999)

seq_num = 0
CHUNK_SIZE = 1024

with open("test.txt", "rb") as f:
    while True:
        chunk = f.read(CHUNK_SIZE)
        if not chunk:
            break 
        
        header = seq_num.to_bytes(4, byteorder='big')
        packet = header + chunk
        
        # VÒNG LẶP TRUYỀN LẠI (Retransmission Loop)
        while True:
            client.sendto(packet, server_address)
            print(f"Đã ném đi mảnh số {seq_num}. Đang đợi xác nhận...")
            
            try:
                # Cố gắng lắng nghe phản hồi ACK từ Server trong 2 giây
                ack_data, _ = client.recvfrom(1024)
                ack_text = ack_data.decode('utf-8')
                
                if ack_text == f"ACK_{seq_num}":
                    print(f"-> Đã nhận {ack_text}. Thành công, chuyển sang mảnh tiếp theo!")
                    break # Nhận đúng ACK thì thoát vòng lặp để gửi mảnh mới
            except socket.timeout:
                # Quá 2 giây mà không thấy ACK, code sẽ nhảy xuống đây
                print(f"[!] Mất kết nối (Timeout). Bắt đầu gửi lại mảnh số {seq_num}...")
        
        seq_num += 1

# Báo hiệu EOF
end_header = (999999).to_bytes(4, byteorder='big')
while True:
    client.sendto(end_header + b'EOF', server_address)
    try:
        ack_data, _ = client.recvfrom(1024)
        if ack_data == b'ACK_EOF':
            print("Đã truyền xong toàn bộ file và Server đã xác nhận thành công!")
            break
    except socket.timeout:
        print("Đang thử gửi lại cờ kết thúc EOF...")