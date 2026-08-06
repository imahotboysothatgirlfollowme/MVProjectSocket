import socket

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 1. Mở file để đọc dưới dạng nhị phân ('rb' - read binary)
with open("test.txt", "rb") as f:
    file_data = f.read() # Đọc toàn bộ nội dung file thành dạng byte

# 2. Ném nguyên cục data của file đó đi
client.sendto(file_data, ("127.0.0.1", 9999))
print("Đã ném toàn bộ nội dung file thành công!")