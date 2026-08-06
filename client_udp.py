import socket

# 1. Khởi tạo socket giống hệt Server
client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 2. Chuẩn bị dữ liệu (Bắt buộc phải chuyển thành dạng byte bằng .encode)
tin_nhan = "Chào Server, em là Bạn B đang test UDP đây!".encode('utf-8')

# 3. Ném thẳng tin nhắn tới địa chỉ và cổng 9999 của Server
client.sendto(tin_nhan, ("127.0.0.1", 9999))
print("Đã ném cục dữ liệu thành công!")