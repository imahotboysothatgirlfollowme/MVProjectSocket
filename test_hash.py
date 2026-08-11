import hashlib

def tinh_ma_bam(file_path):
    # Khởi tạo công cụ băm theo chuẩn MD5
    md5_hash = hashlib.md5()
    
    # Mở file và đọc dữ liệu nhị phân
    with open(file_path, "rb") as f:
        # Đọc từng khối nhỏ (4096 bytes) để không bị tràn RAM nếu file quá to
        while chunk := f.read(4096):
            md5_hash.update(chunk)
            
    # Trả về kết quả là một chuỗi 32 ký tự (hex)
    return md5_hash.hexdigest()

# Gọi hàm để kiểm tra chéo hai file
van_tay_goc = tinh_ma_bam("test.txt")
van_tay_nhan = tinh_ma_bam("file_nhan_duoc.txt")

print(f"Mã băm file gốc  : {van_tay_goc}")
print(f"Mã băm file nhận : {van_tay_nhan}")

if van_tay_goc == van_tay_nhan:
    print("-> CHUẨN XÁC: Hai file giống nhau 100%!")
else:
    print("-> LỖI: Dữ liệu đã bị sai lệch trong quá trình truyền!")