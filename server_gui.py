import hashlib
import socket
import threading
import os
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from rdt_core import rdt_send, rdt_receive

# ==========================================
# CẤU HÌNH SERVER
# ==========================================
HOST = '0.0.0.0'
PORT = 2121
active_clients = {}
SERVER_ROOT = os.path.abspath(os.getcwd())

# Hàm bảo vệ đường dẫn (Giữ nguyên)
def get_safe_path(server_root, current_dir, requested_path):
    safe_requested = requested_path.lstrip('/\\')
    target_path = os.path.abspath(os.path.join(current_dir, safe_requested))
    if os.path.commonpath([server_root, target_path]) == server_root:
        return target_path
    return None

# ==========================================
# CLASS GIAO DIỆN SERVER
# ==========================================
class FTPServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid FTP Server - Control Panel")
        self.root.geometry("850x600")
        self.root.minsize(700, 500)
        self.root.configure(bg="#1E1E1E") # Nền tối Dark Mode cho Server

        self.build_ui()
        
        # Tự động bật Server khi khởi động app
        self.write_log("[SYSTEM] Đang khởi động lõi TCP Server...")
        threading.Thread(target=self.start_tcp_server, daemon=True).start()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", background="#2D2D2D", foreground="white", fieldbackground="#2D2D2D", borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#3C3C3C", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map('Treeview', background=[('selected', '#0078D7')])

        # 1. KHU VỰC BẢNG TRẠNG THÁI (DASHBOARD)
        top_frame = tk.Frame(self.root, bg="#1E1E1E")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        
        tk.Label(top_frame, text="DANH SÁCH CLIENT ĐANG KẾT NỐI", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))

        # Tạo bảng (Treeview)
        columns = ("ip", "user", "status", "mode", "type_mode")
        self.tree = ttk.Treeview(top_frame, columns=columns, show="headings", height=8)
        self.tree.heading("ip", text="IP:PORT")
        self.tree.heading("user", text="USERNAME")
        self.tree.heading("status", text="TRẠNG THÁI")
        self.tree.heading("mode", text="MẠNG (ACT/PASV)")
        self.tree.heading("type_mode", text="ĐỊNH DẠNG/CHẾ ĐỘ")
        
        self.tree.column("ip", width=120, anchor=tk.CENTER)
        self.tree.column("user", width=80, anchor=tk.CENTER)
        self.tree.column("status", width=250, anchor=tk.W)
        self.tree.column("mode", width=120, anchor=tk.CENTER)
        self.tree.column("type_mode", width=120, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True)

        # 2. KHU VỰC LOG TERMINAL
        bot_frame = tk.Frame(self.root, bg="#1E1E1E")
        bot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        
        tk.Label(bot_frame, text="SERVER TERMINAL LOGS", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))
        
        self.log_area = scrolledtext.ScrolledText(bot_frame, state='disabled', bg="#0C0C0C", fg="#CCCCCC", font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    # ==========================================
    # CÁC HÀM CẬP NHẬT GIAO DIỆN (An toàn luồng)
    # ==========================================
    def write_log(self, message):
        """Hàm in log ra màn hình an toàn từ mọi luồng"""
        def _append():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
        self.root.after(0, _append)

    def update_dashboard(self):
        """Hàm cập nhật bảng Treeview an toàn từ mọi luồng"""
        def _refresh():
            # Xóa sạch dữ liệu cũ
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Quét và nhét dữ liệu mới vào
            for c_addr, info in active_clients.items():
                addr_str = f"{c_addr[0]}:{c_addr[1]}"
                type_mode = f"{info['data_type']} / {info['tran_mode']}"
                self.tree.insert("", tk.END, values=(addr_str, info['user'], info['status'], info['mode'], type_mode))
        self.root.after(0, _refresh)

    # ==========================================
    # LÕI MẠNG (TCP SERVER)
    # ==========================================
    def start_tcp_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((HOST, PORT))
        server.listen(5)
        self.write_log(f"[+] TCP ĐANG LẮNG NGHE TẠI {HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            # Gọi một luồng mới cho Client, truyền `self` vào để nó xài giao diện
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

    def handle_client(self, conn, addr):
        self.write_log(f"[+] Có Client kết nối từ {addr}")
        conn.sendall(b"220 Chon Hybrid FTP Server xin chao\r\n")

        # Khởi tạo trạng thái cho Client
        active_clients[addr] = {
            "user": "Chưa rõ", "status": "Đang chờ đăng nhập", 
            "mode": "-", "data_type": "I", "tran_mode": "S",
            "current_dir": SERVER_ROOT
        }
        self.update_dashboard() # Ép giao diện cập nhật ngay lập tức

        is_logged_in = False
        client_udp_addr = None
        is_passive = False
        pasv_sock = None
        temp_user = ""
        rename_from_path = None

        try:
            while True:
                data = conn.recv(1024).decode('utf-8').strip()
                if not data: break
                
                self.write_log(f"[{addr[1]}] Client ra lệnh: {data}")
                parts = data.split(' ', 1)
                cmd = parts[0].upper()
                arg = parts[1] if len(parts) > 1 else ""
                
                if cmd == "USER":
                    temp_user = arg # Lưu tạm tên user lại
                    conn.sendall(b"331 Username OK, can Password\r\n")
                    
                elif cmd == "PASS":
                    if arg == "123456":
                        is_logged_in = True
                        active_clients[addr]["user"] = temp_user
                        active_clients[addr]["status"] = "Đã đăng nhập"
                        conn.sendall(b"230 Dang nhap thanh cong\r\n")
                        self.update_dashboard()
                    else:
                        conn.sendall(b"530 Sai mat khau\r\n")
                        
                elif cmd == "QUIT":
                    conn.sendall(b"221 Tam biet!\r\n")
                    break
                
                elif not is_logged_in:
                    conn.sendall(b"530 Ban chua dang nhap\r\n")
                
                elif cmd == "PORT":
                    # ==========================================
                    # NHÁNH 1: ACTIVE MODE
                    # ==========================================
                    try:
                        p = arg.split(',')
                        if len(p) != 6:
                            raise ValueError("Lenh PORT phai co dung 6 tham so")
                        
                        ip = f"{int(p[0])}.{int(p[1])}.{int(p[2])}.{int(p[3])}"
                        udp_port = (int(p[4]) * 256) + int(p[5])
                        
                        client_udp_addr = (ip, udp_port)
                        is_passive = False
                        active_clients[addr]["mode"] = "ACTIVE"
                        self.update_dashboard()
                        
                        conn.sendall(b"200 PORT ghi nhan thanh cong\r\n")
                        self.write_log(f"[*] Đã lưu tọa độ UDP của Client: {client_udp_addr}")
                        
                    except (IndexError, ValueError):
                        conn.sendall(b"501 Syntax error in parameters\r\n")
                        self.write_log(f"[!] Cảnh báo: Client {addr} gửi lệnh PORT sai cú pháp ('{arg}')")
                
                elif cmd == "PASV":
                    # ==========================================
                    # NHÁNH 2: PASSIVE MODE
                    # ==========================================
                    pasv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    pasv_sock.bind(('0.0.0.0', 0))
                    _, server_port = pasv_sock.getsockname()
                    
                    my_lan_ip = conn.getsockname()[0]
                    ip_pasv = my_lan_ip.replace('.', ',')
                    p1, p2 = server_port // 256, server_port % 256
                    
                    conn.sendall(f"227 Entering Passive Mode ({ip_pasv},{p1},{p2})\r\n".encode('utf-8'))
                    is_passive = True
                    active_clients[addr]["mode"] = "PASSIVE"
                    self.update_dashboard()
                    
                    self.write_log(f"[*] Đã mở cổng PASV ở port {server_port}, đang chờ Client...")
                
                elif cmd == "RETR":
                    if not client_udp_addr and not is_passive:
                        conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                        continue

                    target_file = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], arg)
                    
                    if target_file and os.path.isfile(target_file):
                        conn.sendall(b"150 File ton tai, dang mo luong UDP...\r\n")
                        
                        active_clients[addr]["status"] = f"Đang gửi: {arg[:8]}..."
                        active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                        self.update_dashboard()
                        
                        if is_passive and pasv_sock:
                            try:
                                pasv_sock.settimeout(5.0)
                                _, c_addr = pasv_sock.recvfrom(1024)
                                client_udp_addr = c_addr 
                                pasv_sock.close() 
                                pasv_sock = None
                                self.write_log(f"[*] Bắt được Client điểm danh từ {client_udp_addr}")
                            except socket.timeout:
                                conn.sendall(b"426 Loi: Khong thay Client diem danh!\r\n")
                                active_clients[addr]["status"] = "Lỗi timeout"
                                self.update_dashboard()
                                continue
                        
                        self.write_log(f"[*] Đang bắn file '{arg}' qua UDP...")
                        rdt_send(target_file, client_udp_addr)
                        
                        conn.sendall(b"226 Truyen file hoan tat\r\n")
                        
                        active_clients[addr]["status"] = "Rảnh rỗi"
                        active_clients[addr]["mode"] = "-"
                        self.update_dashboard()
                        
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
                    
                    active_clients[addr]["status"] = f"Đang nhận: {safe_filename[:5]}..."
                    active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                    self.update_dashboard()
                    
                    if not is_passive:
                        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        temp_sock.sendto(b"READY", client_udp_addr)
                        self.write_log(f"[*] Đang hứng luồng UDP từ Client (Active)...")
                        
                        rdt_receive(temp_sock, save_path)
                        temp_sock.close()
                    else:
                        self.write_log(f"[*] Đang hứng luồng UDP từ Client (Passive)...")
                        rdt_receive(pasv_sock, save_path)
                        
                        pasv_sock.close()
                        pasv_sock = None
                    
                    conn.sendall(b"226 Truyen file hoan tat\r\n")
                    self.write_log(f"[*] Đã nhận và lưu file thành công: {save_path}")
                    
                    active_clients[addr]["status"] = "Rảnh rỗi"
                    active_clients[addr]["mode"] = "-" 
                    self.update_dashboard()
                    
                    client_udp_addr = None 
                    is_passive = False

                elif cmd == "LIST":
                    if not client_udp_addr and not is_passive:
                        conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                        continue
                    
                    conn.sendall(b"150 Bat dau gui danh sach file...\r\n")
                    
                    active_clients[addr]["status"] = "Đang lấy danh sách"
                    active_clients[addr]["mode"] = "PASSIVE" if is_passive else "ACTIVE"
                    self.update_dashboard()
                    
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
                    
                    active_clients[addr]["status"] = "Rảnh rỗi"
                    active_clients[addr]["mode"] = "-"
                    self.update_dashboard()
                    
                    client_udp_addr = None
                    is_passive = False

                elif cmd == "HASH":
                    if not arg:
                        conn.sendall(b"501 Thieu ten file tham so\r\n")
                        continue

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
                    if arg.upper() in ['A', 'I']:
                        active_clients[addr]["data_type"] = arg.upper()
                        conn.sendall(f"200 Chuyen doi thanh cong sang kieu TYPE {arg.upper()}\r\n".encode('utf-8'))
                        self.update_dashboard()
                    else:
                        conn.sendall(b"501 Tham so TYPE khong hop le (A hoac I)\r\n")

                elif cmd == "MODE":
                    if arg.upper() in ['S', 'B', 'C']:
                        active_clients[addr]["tran_mode"] = arg.upper()
                        conn.sendall(f"200 Chuyen doi thanh cong sang che do MODE {arg.upper()}\r\n".encode('utf-8'))
                        self.update_dashboard()
                    else:
                        conn.sendall(b"501 Tham so MODE khong hop le (S, B, C)\r\n")

                elif cmd == "NOOP":
                    conn.sendall(b"200 OK\r\n")
                    
                elif cmd == "PWD":
                    client_dir = active_clients[addr]["current_dir"]
                    conn.sendall(f"257 \"{client_dir}\" is current directory\r\n".encode('utf-8'))
                    
                elif cmd == "CWD":
                    target_dir = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], arg)
                    if target_dir and os.path.isdir(target_dir):
                        active_clients[addr]["current_dir"] = target_dir
                        conn.sendall(b"250 CWD command successful\r\n")
                    else:
                        conn.sendall(b"550 Khong tim thay thu muc hoac khong co quyen truy cap\r\n")
                        
                elif cmd == "CDUP":
                    target_dir = get_safe_path(SERVER_ROOT, active_clients[addr]["current_dir"], "..")
                    if target_dir:
                        active_clients[addr]["current_dir"] = target_dir
                        conn.sendall(b"250 CDUP command successful\r\n")
                    else:
                        conn.sendall(b"550 Khong the lui thu muc (Da cham day Root)\r\n")
                
                elif cmd == "QUIT":
                    conn.sendall(b"221 Tam biet!\r\n")
                    break
                else:
                    conn.sendall(b"502 Chua implement day du tren ban GUI\r\n")

        except ConnectionResetError:
            self.write_log(f"[!] Client {addr} ngắt kết nối đột ngột.")
        finally:
            if pasv_sock: pasv_sock.close()
            conn.close()
            if addr in active_clients:
                del active_clients[addr]
            self.write_log(f"[-] Client {addr} đã thoát.")
            self.update_dashboard() # Cập nhật lại bảng để xóa Client đó đi

# ==========================================
# KHỞI CHẠY APP
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    app = FTPServerGUI(root)
    root.mainloop()