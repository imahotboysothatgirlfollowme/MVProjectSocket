import socket

# 1. Khởi tạo socket (AF_INET là chuẩn IPv4, SOCK_DGRAM là chuẩn UDP)
server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 2. Gắn Server vào cổng (port) 9999 trên máy của em (localhost)
server.bind(("127.0.0.1", 9999))
print("Server UDP đang đứng đợi dữ liệu...")

# 3. Tạo một vòng lặp để liên tục hứng dữ liệu
while True:
    # Hứng tối đa 1024 bytes một lần. Nhận được data và địa chỉ người gửi
    data, address = server.recvfrom(1024) 
    
    # In ra màn hình (phải dùng .decode() để dịch dữ liệu byte thành chữ)
    print(f"Nhận được: '{data.decode('utf-8')}' từ địa chỉ {address}")