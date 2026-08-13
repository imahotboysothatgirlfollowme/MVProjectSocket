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

def get_safe_path(server_root, current_dir, requested_path):
    """
    Hàm chuẩn hóa và bảo vệ đường dẫn chống Path Traversal.
    Trả về đường dẫn tuyệt đối nếu an toàn, ngược lại trả về None.
    """
    # 1. Chặn lỗi đường dẫn tuyệt đối: Xóa các dấu slash ở đầu chuỗi (vd: '/etc/passwd' -> 'etc/passwd')
    # Tránh việc os.path.join tự động vứt bỏ thư mục hiện tại.
    safe_requested = requested_path.lstrip('/\\')
    
    # 2. Tính toán đường dẫn đích thực sự
    target_path = os.path.abspath(os.path.join(current_dir, safe_requested))
    
    # 3. Chốt chặn cuối cùng: Kiểm tra xem đích đến có nằm gọn trong SERVER_ROOT không?
    if os.path.commonpath([server_root, target_path]) == server_root:
        return target_path
    
    return None # Cảnh báo rủi ro: Đường dẫn vượt rào!

def handle_client(conn, addr):
    print(f"[+] Có Client kết nối từ {addr}")
    conn.sendall(b"220 Chon Hybrid FTP Server xin chao\r\n")

    # Lấy thư mục hiện tại lúc Server khởi động làm mốc gốc
    SERVER_ROOT = os.path.abspath(os.getcwd())

    # Cập nhật dictionary
    active_clients[addr] = {
        "user": "Chưa rõ", 
        "status": "Đang chờ đăng nhập", 
        "mode": "-",
        "data_type": "I", 
        "tran_mode": "S",
        "current_dir": SERVER_ROOT  # THÊM MỚI: Quản lý thư mục độc lập cho Client này
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
                try:
                    p = arg.split(',')
                    
                    # Bắt buộc phải có đúng 6 phần tử (4 IP, 2 Port)
                    if len(p) != 6:
                        raise ValueError("Lenh PORT phai co dung 6 tham so")
                    
                    # Ép kiểu int cho toàn bộ để bẫy lỗi chữ cái (ValueError sẽ kích hoạt nếu không phải số)
                    ip = f"{int(p[0])}.{int(p[1])}.{int(p[2])}.{int(p[3])}"
                    udp_port = (int(p[4]) * 256) + int(p[5])
                    
                    client_udp_addr = (ip, udp_port)
                    is_passive = False
                    active_clients[addr]["mode"] = "ACTIVE" # Cập nhật trạng thái mode
                    conn.sendall(b"200 PORT ghi nhan thanh cong\r\n")
                    print(f"[*] Da luu toa do UDP cua Client: {client_udp_addr}")
                    
                except (IndexError, ValueError):
                    # Nếu có bất kỳ lỗi nào về index (thiếu tham số) hoặc value (chứa chữ), trả về mã 501
                    conn.sendall(b"501 Syntax error in parameters\r\n")
                    print(f"[!] Canh bao: Client {addr} gui lenh PORT sai cu phap ('{arg}')")
                
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
                if not client_udp_addr and not is_passive:
                    conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                    continue

                # SỬ DỤNG HÀM BẢO VỆ ĐỂ LẤY TARGET FILE
                target_file = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], arg)
                
                if target_file and os.path.isfile(target_file):
                    conn.sendall(b"150 File ton tai, dang mo luong UDP...\r\n")
                    
                    # ---> 1. CẬP NHẬT TRẠNG THÁI & ÉP IN RA MÀN HÌNH NGAY LẬP TỨC
                    active_clients[addr]["status"] = f"Đang gửi: {arg[:8]}..."
                    active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                    print_dashboard()
                    
                    # [TRICK UDP HOLE PUNCHING]: Dò sóng âm của Client
                    if is_passive and pasv_sock:
                        try:
                            pasv_sock.settimeout(5.0)
                            _, c_addr = pasv_sock.recvfrom(1024)
                            client_udp_addr = c_addr 
                            pasv_sock.close() 
                            pasv_sock = None
                            print(f"[*] Bat duoc Client diem danh tu {client_udp_addr}")
                        except socket.timeout:
                            conn.sendall(b"426 Loi: Khong thay Client diem danh!\r\n")
                            # Phải reset trạng thái nếu lỗi
                            active_clients[addr]["status"] = "Lỗi timeout"
                            print_dashboard()
                            continue
                    
                    print(f"[*] Dang ban file '{arg}' qua UDP...")
                    rdt_send(target_file, client_udp_addr)
                    
                    conn.sendall(b"226 Truyen file hoan tat\r\n")
                    
                    # ---> 2. RESET TRẠNG THÁI VÀ ÉP IN LẠI XÁC NHẬN ĐÃ XONG
                    active_clients[addr]["status"] = "Rảnh rỗi"
                    active_clients[addr]["mode"] = "-"
                    print_dashboard()
                    
                    client_udp_addr = None 
                    is_passive = False
                else:
                    conn.sendall(b"550 Khong tim thay file\r\n")

            elif cmd == "STOR":
                if not client_udp_addr and not is_passive:
                    conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                    continue
                
                safe_filename = os.path.basename(arg)
                save_path = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], f"server_recv_{safe_filename}")
                
                if not save_path:
                    conn.sendall(b"553 Ten file khong hop le\r\n")
                    continue
                
                conn.sendall(b"150 San sang nhan file, dang mo luong UDP...\r\n")
                
                # ---> 1. Cập nhật trạng thái
                active_clients[addr]["status"] = f"Đang nhận: {safe_filename[:5]}..."
                active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                
                # ---> 2. ÉP IN RA MÀN HÌNH NGAY LẬP TỨC TRƯỚC KHI BỊ TREO BỞI UDP
                print_dashboard()
                
                if not is_passive:
                    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    temp_sock.sendto(b"READY", client_udp_addr)
                    print(f"[*] Dang hung luong UDP tu Client (Active)...")
                    
                    rdt_receive(temp_sock, save_path)
                    temp_sock.close()
                else:
                    print(f"[*] Dang hung luong UDP tu Client (Passive)...")
                    rdt_receive(pasv_sock, save_path)
                    
                    pasv_sock.close()
                    pasv_sock = None
                
                # Báo thành công
                conn.sendall(b"226 Truyen file hoan tat\r\n")
                print(f"[*] Đã nhận và lưu file thành công: {save_path}")
                
                # ---> 3. Reset trạng thái và ép in lại lần nữa để xác nhận xong
                active_clients[addr]["status"] = "Rảnh rỗi"
                active_clients[addr]["mode"] = "-" 
                print_dashboard()
                
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
                
                # ---> 1. CẬP NHẬT TRẠNG THÁI & ÉP IN RA MÀN HÌNH NGAY LẬP TỨC
                active_clients[addr]["status"] = "Đang lấy danh sách"
                active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                print_dashboard()
                
                listing = ""
                client_dir = active_clients[addr]["current_dir"]

                for f in os.listdir(client_dir):
                    full_path = os.path.join(client_dir, f)
                    if os.path.isfile(full_path):
                        size = os.path.getsize(full_path)
                        listing += f"-rwxr-xr-x 1 owner group {size:8} {f}\r\r\n"
                    elif os.path.isdir(full_path):
                        listing += f"drwxr-xr-x 1 owner group        0 {f}\r\r\n"

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
                
                # ---> 2. RESET TRẠNG THÁI VÀ ÉP IN LẠI XÁC NHẬN ĐÃ XONG
                active_clients[addr]["status"] = "Rảnh rỗi"
                active_clients[addr]["mode"] = "-"
                print_dashboard()
                
                client_udp_addr = None
                is_passive = False

            elif cmd == "HASH":
                if not arg:
                    conn.sendall(b"501 Thieu ten file tham so\r\n")
                    continue

                # SỬ DỤNG HÀM BẢO VỆ
                target_file = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], arg)
                
                if target_file and os.path.isfile(target_file):
                    hasher = hashlib.sha256()
                    with open(target_file, "rb") as f: 
                        hasher.update(f.read())
                    digest = hasher.hexdigest()
                    conn.sendall(f"200 {digest}\r\n".encode('utf-8'))
                else:
                    conn.sendall(b"550 Khong tim thay file hoac truy cap bi tu choi\r\n")

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

            elif cmd == "NOOP":
                # Lệnh giữ kết nối (Ping)
                conn.sendall(b"200 OK\r\n")
                
            elif cmd == "PWD":
                # Lấy thư mục riêng của client thay vì os.getcwd()
                client_dir = active_clients[addr]["current_dir"]
                conn.sendall(f"257 \"{client_dir}\" is current directory\r\n".encode('utf-8'))
                
            elif cmd == "CWD":
                # SỬ DỤNG HÀM BẢO VỆ
                target_dir = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], arg)
                
                if target_dir and os.path.isdir(target_dir):
                    active_clients[addr]["current_dir"] = target_dir
                    conn.sendall(b"250 CWD command successful\r\n")
                else:
                    conn.sendall(b"550 Khong tim thay thu muc hoac khong co quyen truy cap\r\n")
                    
            elif cmd == "CDUP":
                # Lùi 1 cấp ('..')
                target_dir = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], "..")
                
                if target_dir:
                    active_clients[addr]["current_dir"] = target_dir
                    conn.sendall(b"250 CDUP command successful\r\n")
                else:
                    conn.sendall(b"550 Khong the lui thu muc (Da cham day Root)\r\n")

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
def print_dashboard():
    """Hàm độc lập để in bảng trạng thái"""
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

def monitor_dashboard():
    """Luồng chạy ngầm vẫn giữ nhịp 10s cho các trạng thái treo"""
    while True:
        time.sleep(10) 
        print_dashboard()

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