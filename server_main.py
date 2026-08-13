import hashlib
import socket
import threading
import os
import time
from rdt_core import rdt_send, rdt_receive

# (Lắng nghe từ tất cả các máy trong mạng LAN):
HOST = '0.0.0.0'
PORT = 2121

active_clients = {}

def handle_client(conn, addr):
    print(f"[+] Có Client kết nối từ {addr}")
    conn.sendall(b"220 Chon Hybrid FTP Server xin chao\r\n")

    # --- ĐĂNG KÝ CLIENT VÀO HỆ THỐNG ---
    active_clients[addr] = {
        "user": "Chưa rõ", 
        "status": "Đang chờ đăng nhập", 
        "mode": "-",
        "data_type": "I",  # Default I = Image/Binary
        "tran_mode": "S"   # Default S = Stream
    }
    
    is_logged_in = False
    client_udp_addr = None # Tọa độ dùng cho Active Mode
    
    # 2 biến mới bổ sung phục vụ Passive Mode
    is_passive = False
    pasv_sock = None 

    # Dùng biến phụ để lưu tạm tên user khi họ gõ lệnh USER
    temp_user = ""
    
    try:
        while True:
            data = conn.recv(1024).decode('utf-8').strip()
            if not data: break
            
            print(f"[{addr[1]}] Client ra lệnh: {data}")
            parts = data.split(' ', 1)
            cmd = parts[0].upper()
            arg = parts[1] if len(parts) > 1 else ""
            
            if cmd == "USER":
                temp_user = arg # Lưu tạm tên user lại
                conn.sendall(b"331 Username OK, can Password\r\n")
            elif cmd == "PASS":
                if arg == "123456":
                    is_logged_in = True
                    # --- CẬP NHẬT TRẠNG THÁI: ĐÃ ĐĂNG NHẬP ---
                    active_clients[addr]["user"] = temp_user
                    active_clients[addr]["status"] = "Đã đăng nhập"
                    conn.sendall(b"230 Dang nhap thanh cong\r\n")
                else:
                    conn.sendall(b"530 Sai mat khau\r\n")
            elif cmd == "QUIT":
                conn.sendall(b"221 Tam biet!\r\n")
                break
            
            elif not is_logged_in:
                conn.sendall(b"530 Ban chua dang nhap\r\n")
            
            elif cmd == "PORT":
                # ==========================================
                # NHÁNH 1: ACTIVE MODE (Ghi nhận cổng của Client)
                # ==========================================
                p = arg.split(',')
                ip = f"{p[0]}.{p[1]}.{p[2]}.{p[3]}"
                udp_port = (int(p[4]) * 256) + int(p[5])
                
                client_udp_addr = (ip, udp_port)
                is_passive = False
                active_clients[addr]["mode"] = "ACTIVE" # Cập nhật trạng thái mode
                conn.sendall(b"200 PORT ghi nhan thanh cong\r\n")
                print(f"[*] Da luu toa do UDP cua Client: {client_udp_addr}")
                
            elif cmd == "PASV":
                # ==========================================
                # NHÁNH 2: PASSIVE MODE (Tự mở cổng và báo cho Client)
                # ==========================================
                pasv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                pasv_sock.bind(('0.0.0.0', 0)) # Sửa thành 0.0.0.0
                _, server_port = pasv_sock.getsockname()
                
                # Lấy IP LAN thực tế mà Server đang dùng để chat với Client này
                my_lan_ip = conn.getsockname()[0]
                ip_pasv = my_lan_ip.replace('.', ',')
                
                p1, p2 = server_port // 256, server_port % 256
                
                # Gửi tọa độ mạng LAN thực tế thay vì 127.0.0.1
                conn.sendall(f"227 Entering Passive Mode ({ip_pasv},{p1},{p2})\r\n".encode('utf-8'))
                is_passive = True
                print(f"[*] Da mo cong PASV o port {server_port}, dang cho Client...")
                
            elif cmd == "RETR":
                # ==========================================
                # XỬ LÝ LỆNH TẢI FILE CHO CẢ 2 CHẾ ĐỘ
                # ==========================================
                if not client_udp_addr and not is_passive:
                    conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                    continue
                
                if os.path.isfile(arg):
                    conn.sendall(b"150 File ton tai, dang mo luong UDP...\r\n")
                    
                    # [TRICK UDP HOLE PUNCHING]: Dò sóng âm của Client
                    if is_passive and pasv_sock:
                        try:
                            # Đợi tối đa 5 giây xem Client có "điểm danh" không
                            pasv_sock.settimeout(5.0)
                            _, c_addr = pasv_sock.recvfrom(1024)
                            client_udp_addr = c_addr # Bắt được IP/Port của Client rồi!
                            
                            pasv_sock.close() # Lấy được rồi thì đóng cửa ngầm
                            pasv_sock = None
                            print(f"[*] Bat duoc Client diem danh tu {client_udp_addr}")
                        except socket.timeout:
                            conn.sendall(b"426 Loi: Khong thay Client diem danh!\r\n")
                            continue
                    
                    print(f"[*] Dang ban file '{arg}' qua UDP...")
                    # Dùng chung 1 hàm rdt_send ném file đi, dù là Active hay Passive
                    rdt_send(arg, client_udp_addr)
                    
                    conn.sendall(b"226 Truyen file hoan tat\r\n")
                    
                    # Truyền xong phải Reset lại thông tin để an toàn cho lần tải sau
                    client_udp_addr = None 
                    is_passive = False
                else:
                    conn.sendall(b"550 Khong tim thay file\r\n")

            elif cmd == "STOR":
                # ==========================================
                # XỬ LÝ LỆNH UPLOAD TỪ CLIENT
                # ==========================================
                if not client_udp_addr and not is_passive:
                    conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                    continue
                
                # Để tránh đè file hệ thống, gắn thêm chữ 'server_recv_' vào tên file
                save_path = f"server_recv_{arg}"
                conn.sendall(b"150 San sang nhan file, dang mo luong UDP...\r\n")
                
                if not is_passive:
                    # ACTIVE MODE: Server phải chủ động mở cổng UDP và ném chữ READY cho Client biết chỗ
                    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    temp_sock.sendto(b"READY", client_udp_addr)
                    print(f"[*] Dang hung luong UDP tu Client (Active)...")
                    
                    rdt_receive(temp_sock, save_path)
                    temp_sock.close()
                else:
                    # PASSIVE MODE: Server đã mở cổng pasv_sock từ lúc Client gọi lệnh PASV rồi, cứ thế lấy ra hứng thôi
                    print(f"[*] Dang hung luong UDP tu Client (Passive)...")
                    rdt_receive(pasv_sock, save_path)
                    
                    pasv_sock.close()
                    pasv_sock = None
                
                # Báo thành công
                conn.sendall(b"226 Truyen file hoan tat\r\n")
                print(f"[*] Đã nhận và lưu file thành công: {save_path}")
                
                # Reset trạng thái
                client_udp_addr = None 
                is_passive = False

            elif cmd == "LIST":
                # ==========================================
                # XỬ LÝ LỆNH LIỆT KÊ DANH SÁCH FILE
                # ==========================================
                if not client_udp_addr and not is_passive:
                    conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                    continue
                
                conn.sendall(b"150 Bat dau gui danh sach file...\r\n")
                
                # Quét thư mục hiện tại của Server để lập danh sách
                listing = ""
                for f in os.listdir('.'):
                    if os.path.isfile(f):
                        size = os.path.getsize(f)
                        listing += f"-rwxr-xr-x 1 owner group {size:8} {f}\r\r\n"
                    elif os.path.isdir(f):
                        listing += f"drwxr-xr-x 1 owner group        0 {f}\r\r\n"
                
                # Mẹo nhỏ: Ghi nội dung ra file tạm để tận dụng hàm rdt_send có sẵn
                temp_filename = "temp_server_list.txt"
                with open(temp_filename, "w", encoding="utf-8") as tf:
                    tf.write(listing)
                
                if is_passive and pasv_sock:
                    try:
                        pasv_sock.settimeout(5.0)
                        _, c_addr = pasv_sock.recvfrom(1024)
                        client_udp_addr = c_addr
                        pasv_sock.close()
                        pasv_sock = None
                    except socket.timeout:
                        pass
                
                rdt_send(temp_filename, client_udp_addr)
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                
                conn.sendall(b"226 Truyen danh sach hoan tat\r\n")
                client_udp_addr = None
                is_passive = False

            elif cmd == "HASH":
                # ==========================================
                # XỬ LÝ LỆNH KIỂM TRA MÃ BĂM SHA-256
                # ==========================================
                if not arg:
                    conn.sendall(b"501 Thieu ten file tham so\r\n")
                    continue
                
                if os.path.isfile(arg):
                    hasher = hashlib.sha256()
                    with open(arg, "rb") as f:
                        hasher.update(f.read())
                    digest = hasher.hexdigest()
                    conn.sendall(f"200 {digest}\r\n".encode('utf-8'))
                    print(f"[*] Đã gửi SHA-256 của file '{arg}': {digest}")
                else:
                    conn.sendall(b"550 Khong tim thay file\r\n")

            elif cmd == "TYPE":
                # ==========================================
                # ĐỊNH DẠNG DỮ LIỆU (A = ASCII, I = Binary)
                # ==========================================
                if arg.upper() in ['A', 'I']:
                    active_clients[addr]["data_type"] = arg.upper()
                    conn.sendall(f"200 Chuyen doi thanh cong sang kieu TYPE {arg.upper()}\r\n".encode('utf-8'))
                else:
                    conn.sendall(b"501 Tham so TYPE khong hop le (A hoac I)\r\n")

            elif cmd == "MODE":
                # ==========================================
                # CHẾ ĐỘ TRUYỀN (S = Stream, B = Block, C = Compressed)
                # ==========================================
                if arg.upper() in ['S', 'B', 'C']:
                    active_clients[addr]["tran_mode"] = arg.upper()
                    conn.sendall(f"200 Chuyen doi thanh cong sang che do MODE {arg.upper()}\r\n".encode('utf-8'))
                else:
                    conn.sendall(b"501 Tham so MODE khong hop le (S, B, C)\r\n")

            else:
                conn.sendall(b"502 Lenh khong hop le\r\n")

                
    except ConnectionResetError:
        pass
    finally:
        # --- DỌN DẸP KHI CLIENT THOÁT ---
        if pasv_sock: pasv_sock.close()
        conn.close()
        if addr in active_clients:
            del active_clients[addr] # Xóa khỏi danh sách theo dõi
        print(f"[-] Client {addr} ngat ket noi")

# --- HÀM THEO DÕI TRẠNG THÁI CLIENT (DASHBOARD) ---
def monitor_dashboard():
    while True:
        time.sleep(10) # Cứ 10 giây in ra một lần
        print("\n" + "="*50)
        print(f" DANH SÁCH CLIENT ĐANG ONLINE (Tổng: {len(active_clients)})")
        print("="*50)
        print(f"{'IP:PORT':<20} | {'USERNAME':<10} | {'TRẠNG THÁI':<18} | {'CHẾ ĐỘ'}")
        print("-" * 50)
        
        if not active_clients:
            print("Không có ai đang kết nối...")
        else:
            for c_addr, info in active_clients.items():
                addr_str = f"{c_addr[0]}:{c_addr[1]}"
                print(f"{addr_str:<20} | {info['user']:<10} | {info['status']:<18} | {info['mode']}")
        print("="*50 + "\n")

# --- LUỒNG MAIN KHỞI ĐỘNG SERVER ---
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(5)
print(f"[*] BỘ NÃO TCP ĐANG CHẠY TẠI {HOST}:{PORT}")

# Bật luồng Dashboard
threading.Thread(target=monitor_dashboard, daemon=True).start()

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()