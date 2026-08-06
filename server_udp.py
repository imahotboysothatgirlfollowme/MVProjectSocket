import socket

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(("127.0.0.1", 9999))
print("Server đang đợi hứng file...")

# Hứng dữ liệu (tạm thời để buffer lớn xíu: 4096 bytes)
data, address = server.recvfrom(4096) 

# Mở một file mới để ghi dữ liệu nhị phân vào ('wb' - write binary)
with open("file_nhan_duoc.txt", "wb") as f:
    f.write(data)

print(f"Đã nhận file từ {address} và lưu thành công!")