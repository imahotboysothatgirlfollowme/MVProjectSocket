import hashlib
import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import simpledialog, filedialog
import re  # Thêm thư viện này để bóc tách IP/Port của lệnh PASV
from rdt_core import rdt_receive, rdt_send
import os


class FTPClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid FTP Client")
        self.root.geometry("800x550")
        self.root.minsize(700, 500)

        # Định nghĩa các biến lưu trữ thông tin nhập liệu
        self.ip_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="2121")
        self.user_var = tk.StringVar(value="admin")
        self.pass_var = tk.StringVar(value="123456")

        self.build_ui()

    def build_ui(self):
        self.root.title("Hybrid FTP Client")
        self.root.geometry("900x550")
        self.root.minsize(800, 500)
        self.root.configure(bg="#F3F4F6") # Màu nền xám nhạt hiện đại
        
        # --- CẤU HÌNH STYLE (Giao diện phẳng, tinh tế) ---
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#F3F4F6")
        style.configure("Sidebar.TFrame", background="#FFFFFF")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), background="#FFFFFF", foreground="#1F2937")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), background="#FFFFFF", foreground="#6B7280")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        
        # --- BỐ CỤC CHÍNH (Chia 2 cột Left - Right) ---
        main_container = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bd=0, bg="#E5E7EB")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ==========================================
        # 1. SIDEBAR (CỘT TRÁI - Thông tin kết nối)
        # ==========================================
        sidebar = ttk.Frame(main_container, style="Sidebar.TFrame", width=280)
        main_container.add(sidebar, minsize=280)

        
        # Cấu trúc nhập liệu (Form)
        form_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
        # Thêm pady=(20, 0) để đẩy form xuống một chút cho đẹp sau khi xóa tiêu đề
        form_frame.pack(fill=tk.X, padx=20, pady=(20, 0)) 
        
        def create_input(parent, label_text, default_val, is_password=False):
            ttk.Label(parent, text=label_text, font=("Segoe UI", 9, "bold"), background="#FFFFFF", foreground="#374151").pack(anchor=tk.W, pady=(10, 2))
            entry = ttk.Entry(parent, font=("Consolas", 10), show="*" if is_password else "")
            entry.insert(0, default_val)
            entry.pack(fill=tk.X, ipady=4)
            return entry

        self.ent_host = create_input(form_frame, "Server IP:", "127.0.0.1")
        self.ent_port = create_input(form_frame, "Command Port:", "2121")
        self.ent_user = create_input(form_frame, "Username:", "admin")
        self.ent_pass = create_input(form_frame, "Password:", "123456", is_password=True)
        
        # Cấu hình Passive Mode (Vẫn giữ dạng Checkbox)
        self.use_pasv_var = tk.BooleanVar(value=True) 
        chk_pasv = tk.Checkbutton(sidebar, text=" Bật Passive Mode (PASV)", variable=self.use_pasv_var, 
                                  bg="#FFFFFF", font=("Segoe UI", 9), activebackground="#FFFFFF")
        chk_pasv.pack(anchor=tk.W, padx=20, pady=20)
        
        # Nút Kết nối (Đã fix lỗi command=self.start_connection)
        self.btn_connect = tk.Button(sidebar, text="KẾT NỐI SERVER", bg="#2563EB", fg="white", 
                                     font=("Segoe UI", 10, "bold"), relief=tk.FLAT, 
                                     cursor="hand2", command=self.start_connection)
        self.btn_connect.pack(fill=tk.X, padx=20, pady=(0, 20), ipady=8)

        # ==========================================
        # 2. MAIN CONTENT (CỘT PHẢI - Thao tác & Log)
        # ==========================================
        content_frame = ttk.Frame(main_container)
        main_container.add(content_frame)
        
        # Thanh công cụ (Action Bar)
        action_frame = tk.Frame(content_frame, bg="#FFFFFF", bd=1, relief=tk.SOLID)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        # Đổi viền khung cho mỏng và tinh tế hơn
        action_frame.config(highlightbackground="#D1D5DB", highlightcolor="#D1D5DB", highlightthickness=1, bd=0)
        
        # Chứa các nút lệnh ngang
        btn_container = tk.Frame(action_frame, bg="#FFFFFF")
        btn_container.pack(padx=15, pady=15, anchor=tk.W)
        
        self.btn_list = ttk.Button(btn_container, text="Liệt kê (LIST)", style="Action.TButton", state="disabled", command=self.list_files)
        self.btn_list.grid(row=0, column=0, padx=(0, 10))
        
        self.btn_retr = ttk.Button(btn_container, text="Tải về (RETR)", style="Action.TButton", state="disabled", command=self.download_file)
        self.btn_retr.grid(row=0, column=1, padx=(0, 10))
        
        self.btn_stor = ttk.Button(btn_container, text="Tải lên (STOR)", style="Action.TButton", state="disabled", command=self.upload_file)
        self.btn_stor.grid(row=0, column=2, padx=(0, 10))
        
        self.btn_hash = ttk.Button(btn_container, text="Kiểm tra HASH", style="Action.TButton", state="disabled", command=self.verify_hash)
        self.btn_hash.grid(row=0, column=3, padx=(0, 10))

        # Khu vực Terminal Log (Giả lập màn hình code Console)
        log_frame = tk.Frame(content_frame, bg="#1E1E1E")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        log_label = tk.Label(log_frame, text="TERMINAL OUTPUT", bg="#333333", fg="#CCCCCC", font=("Consolas", 9, "bold"), anchor=tk.W)
        log_label.pack(fill=tk.X, ipady=4, padx=10)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', bg="#1E1E1E", fg="#D4D4D4", 
                                                  font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # Cấu hình màu sắc cho log để dễ phân biệt
        self.log_area.tag_config("client", foreground="#4FC1FF") # Xanh lam nhạt (Mã lệnh Client)
        self.log_area.tag_config("server", foreground="#B5CEA8") # Xanh lá mạ (Phản hồi Server)
        self.log_area.tag_config("error", foreground="#F44747")  # Đỏ (Báo lỗi)
        
        self.write_log("Khởi tạo Hybrid FTP Client thành công. Sẵn sàng kết nối...", is_client=True)

    def write_log(self, message, is_client=True):
        self.log_area.config(state='normal')
        
        if message.startswith("❌"):
            tag = "error"
        else:
            tag = "client" if is_client else "server"
            
        prefix = "➜ " if is_client else "✓ "
        if message.startswith("===") or message.startswith("❌") or message.startswith("✅"):
            prefix = "" # Không nối tiền tố vào các câu báo cáo đặc biệt
            
        self.log_area.insert(tk.END, f"{prefix}{message}\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    import socket
    import threading
    from tkinter import messagebox

    def start_connection(self):
        """Hàm này được gọi khi bấm nút. Nó sẽ kích hoạt một luồng phụ để chạy kết nối."""
        # Vô hiệu hóa nút bấm tạm thời để tránh user spam click
        self.btn_connect.config(state="disabled")
        
        # Lấy dữ liệu từ giao diện
        ip = self.ip_var.get().strip()
        port = int(self.port_var.get().strip())
        user = self.user_var.get().strip()
        password = self.pass_var.get().strip()
        
        # Mở luồng phụ để không làm đơ giao diện
        threading.Thread(target=self._login_flow, args=(ip, port, user, password), daemon=True).start()

    def _send_cmd(self, sock, command):
        """Hàm tự thiết kế để ném lệnh TCP và chờ phản hồi"""
        self.write_log(command, is_client=True)
        sock.sendall(f"{command}\r\n".encode('utf-8'))
        
        # Hứng phản hồi từ Server
        response = sock.recv(1024).decode('utf-8').strip()
        self.write_log(response, is_client=False)
        return response

    def _login_flow(self, ip, port, user, password):
        """Luồng xử lý quy trình 3 bước xác thực TCP"""
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            # BƯỚC 1: Gọi cửa (Connect)
            self.write_log(f"Đang kết nối đến {ip}:{port}...")
            self.tcp_sock.connect((ip, port))
            
            # Hứng câu chào 220 của Server khi vừa kết nối xong
            welcome_msg = self.tcp_sock.recv(1024).decode('utf-8').strip()
            self.write_log(welcome_msg, is_client=False)
            
            # BƯỚC 2: Gửi Username
            res_user = self._send_cmd(self.tcp_sock, f"USER {user}")
            if not res_user.startswith("331"):
                raise Exception("Server từ chối Username!")
                
            # BƯỚC 3: Gửi Password
            res_pass = self._send_cmd(self.tcp_sock, f"PASS {password}")
            if res_pass.startswith("230"):
                self.write_log("ĐĂNG NHẬP THÀNH CÔNG! Đã mở khóa các tính năng.")
                # Mở khóa các nút thao tác file
                self.btn_list.config(state="normal")
                self.btn_retr.config(state="normal")
                self.btn_stor.config(state="normal")
                self.btn_hash.config(state="normal")
                # Đổi tên nút kết nối
                self.btn_connect.config(text="Đã kết nối")
            else:
                raise Exception("Sai mật khẩu hoặc bị từ chối!")
                
        except Exception as e:
            self.write_log(f"LỖI KẾT NỐI: {str(e)}")
            messagebox.showerror("Lỗi", f"Không thể kết nối hoặc đăng nhập:\n{str(e)}")
            self.btn_connect.config(state="normal", text="Kết nối Server")
            if hasattr(self, 'tcp_sock'):
                self.tcp_sock.close()

    def download_file(self):
        """Hàm kích hoạt khi bấm nút Tải về"""
        # Bật hộp thoại hỏi tên file muốn tải
        filename = simpledialog.askstring("Tải file", "Nhập tên file muốn tải từ Server:")
        if not filename:
            return
            
        # Ném tác vụ tải file vào một luồng riêng để giao diện không bị treo
        threading.Thread(target=self._download_flow, args=(filename,), daemon=True).start()

    def _download_flow(self, filename):
        """Luồng xử lý gộp TCP và UDP (Hỗ trợ cả Active và Passive)"""
        try:
            # Kiểm tra xem user có đánh dấu tích vào ô PASV không
            is_passive = self.use_pasv_var.get()
            
            # Khởi tạo công cụ hứng UDP (Cả 2 chế độ đều cần)
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Khai báo sẵn biến tọa độ của Server để dùng cho Passive Mode
            server_data_addr = None 
            
            if not is_passive:
                # === ACTIVE MODE ===
                self.write_log("Đang chạy ACTIVE: Gửi cổng của Client lên Server...")
                data_sock.bind(('0.0.0.0', 0)) # Sửa thành 0.0.0.0
                _, client_port = data_sock.getsockname()
                
                # Lấy IP LAN thực tế của Client thay vì 127.0.0.1
                my_lan_ip = self.tcp_sock.getsockname()[0]
                ip_format = my_lan_ip.replace('.', ',')
                
                p1, p2 = client_port // 256, client_port % 256
                res_port = self._send_cmd(self.tcp_sock, f"PORT {ip_format},{p1},{p2}")
                if not res_port.startswith("200"):
                    raise Exception("Server từ chối lệnh PORT!")
            else:
                # ==========================================
                # NHÁNH 2: PASSIVE MODE (Lệnh PASV)
                # ==========================================
                self.write_log("Đang chạy chế độ PASSIVE (Server mở cổng)...")
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                if not res_pasv.startswith("227"):
                    raise Exception("Server không phản hồi mã 227 PASV!")
                    
                # Bóc tách chuỗi "227 Entering Passive Mode (127,0,0,1,19,136)"
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                if not match:
                    raise Exception("Không đọc được tọa độ từ Server!")
                    
                parts = match.group(1).split(',')
                server_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}"
                server_port = (int(parts[4]) * 256) + int(parts[5])
                server_data_addr = (server_ip, server_port)
                self.write_log(f"[*] Đã xác định Server đang đợi ở UDP port: {server_port}")

            # ==========================================
            # GIAO ĐOẠN 3: LẤY FILE VỀ
            # ==========================================
            res_retr = self._send_cmd(self.tcp_sock, f"RETR {filename}")
            if res_retr.startswith("150"):
                self.write_log(f"Đang hứng luồng dữ liệu UDP cho file '{filename}'...")
                
                # [MẸO ẨN]: Vì UDP không có kết nối, nếu chạy Passive, Server mở cổng nhưng không biết Client ở đâu để ném file!
                # Do đó, Client phải ném 1 gói tin giả ("READY") vào cổng của Server để "điểm danh", 
                # giúp Server nắm được địa chỉ của Client rồi mới bắn file ngược lại.
                if is_passive:
                    data_sock.sendto(b"READY", server_data_addr)
                
                save_path = f"downloaded_{filename}" 
                rdt_receive(data_sock, save_path)
                
                res_226 = self.tcp_sock.recv(1024).decode('utf-8').strip()
                self.write_log(res_226, is_client=False)
                self.write_log(f"Đã lưu file thành công: {save_path}")
            else:
                self.write_log("Server không cho phép tải (Không tìm thấy file).")
                
        except Exception as e:
            self.write_log(f"Lỗi truyền tải: {str(e)}")
        finally:
            data_sock.close()

    def upload_file(self):
        """Hàm kích hoạt khi bấm nút Tải lên"""
        # Mở hộp thoại để người dùng chọn file từ máy
        filepath = filedialog.askopenfilename(title="Chọn file muốn tải lên Server")
        if not filepath:
            return
            
        # Ném vào luồng phụ
        threading.Thread(target=self._upload_flow, args=(filepath,), daemon=True).start()

    def _upload_flow(self, filepath):
        """Luồng Tải file lên Server (Hỗ trợ Active & Passive)"""
        try:
            filename = os.path.basename(filepath)
            is_passive = self.use_pasv_var.get()
            
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_data_addr = None 
            
            if not is_passive:
                # === ACTIVE MODE ===
                self.write_log("Đang chạy ACTIVE: Gửi cổng của Client lên Server...")
                data_sock.bind(('0.0.0.0', 0)) # Sửa thành 0.0.0.0
                _, client_port = data_sock.getsockname()
                
                # Lấy IP LAN thực tế của Client thay vì 127.0.0.1
                my_lan_ip = self.tcp_sock.getsockname()[0]
                ip_format = my_lan_ip.replace('.', ',')
                
                p1, p2 = client_port // 256, client_port % 256
                res_port = self._send_cmd(self.tcp_sock, f"PORT {ip_format},{p1},{p2}")
                if not res_port.startswith("200"):
                    raise Exception("Server từ chối lệnh PORT!")
            else:
                # === PASSIVE MODE ===
                self.write_log("Đang chạy PASSIVE: Lấy cổng từ Server...")
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                if not res_pasv.startswith("227"):
                    raise Exception("Server không phản hồi mã 227 PASV!")
                    
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                parts = match.group(1).split(',')
                server_port = (int(parts[4]) * 256) + int(parts[5])
                server_data_addr = (f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}", server_port)

            # Gửi lệnh STOR để báo Server chuẩn bị nhận
            res_stor = self._send_cmd(self.tcp_sock, f"STOR {filename}")
            if res_stor.startswith("150"):
                self.write_log(f"Đang đẩy file '{filename}' lên Server qua UDP...")
                
                if not is_passive:
                    # [TRICK ACTIVE MODE]: Chờ Server ném gói "READY" vào cổng Client để lấy IP/Port của Server
                    data_sock.settimeout(5.0)
                    _, s_addr = data_sock.recvfrom(1024)
                    server_data_addr = s_addr
                
                # GỌI VŨ KHÍ RDT ĐỂ NÉM FILE ĐI
                rdt_send(filepath, server_data_addr)
                
                # Chờ Server báo đã nhận đủ
                res_226 = self.tcp_sock.recv(1024).decode('utf-8').strip()
                self.write_log(res_226, is_client=False)
                self.write_log(f"Upload hoàn tất: {filename}")
                
                # Thêm dòng này để báo cho người dùng biết tên file đã lưu trên Server
                self.write_log(f"Đã lưu trên Server với tên: server_recv_{filename}")
            else:
                self.write_log("Server không cho phép tải lên.")
                
        except Exception as e:
            self.write_log(f"Lỗi Upload: {str(e)}")
        finally:
            data_sock.close()

    def list_files(self):
        """Hàm kích hoạt lấy danh sách tập tin từ Server qua UDP"""
        threading.Thread(target=self._list_flow, daemon=True).start()

    def _list_flow(self):
        try:
            is_passive = self.use_pasv_var.get()
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_data_addr = None
            
            if not is_passive:
                # === ACTIVE MODE ===
                self.write_log("Đang chạy ACTIVE: Gửi cổng của Client lên Server...")
                data_sock.bind(('0.0.0.0', 0)) # Sửa thành 0.0.0.0
                _, client_port = data_sock.getsockname()
                
                # Lấy IP LAN thực tế của Client thay vì 127.0.0.1
                my_lan_ip = self.tcp_sock.getsockname()[0]
                ip_format = my_lan_ip.replace('.', ',')
                
                p1, p2 = client_port // 256, client_port % 256
                res_port = self._send_cmd(self.tcp_sock, f"PORT {ip_format},{p1},{p2}")
                if not res_port.startswith("200"):
                    raise Exception("Server từ chối lệnh PORT!")
            else:
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                parts = match.group(1).split(',')
                server_data_addr = (f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}", (int(parts[4])*256)+int(parts[5]))

            res_list = self._send_cmd(self.tcp_sock, "LIST")
            if res_list.startswith("150"):
                self.write_log("Đang hứng danh sách tập tin qua UDP...")
                if not is_passive:
                    data_sock.settimeout(5.0)
                    _, s_addr = data_sock.recvfrom(1024)
                    server_data_addr = s_addr
                else:
                    data_sock.sendto(b"READY", server_data_addr)
                    
                save_name = "client_received_list.txt"
                rdt_receive(data_sock, save_name)
                
                # Đọc file danh sách và in ra màn hình nhật ký GUI
                with open(save_name, "r", encoding="utf-8") as f:
                    content = f.read()
                self.write_log("=== DANH SÁCH TẬP TIN TRÊN SERVER ===")
                for line in content.splitlines():
                    if line.strip():
                        self.write_log(line, is_client=False)
                self.write_log("=====================================")
                
                if os.path.exists(save_name): 
                    os.remove(save_name)
                
                res_226 = self.tcp_sock.recv(1024).decode('utf-8').strip()
                self.write_log(res_226, is_client=False)
        except Exception as e:
            self.write_log(f"Lỗi lấy danh sách: {e}")
        finally:
            data_sock.close()

    def verify_hash(self):
        """Hàm kiểm tra mã băm SHA-256 đối chiếu file"""
        filename = simpledialog.askstring("Kiểm tra HASH", "Nhập tên file trên Server cần kiểm tra:")
        if not filename: return
        local_path = filedialog.askopenfilename(title=f"Chọn file local tương ứng với '{filename}' để so sánh")
        if not local_path: return
        
        def _task():
            res = self._send_cmd(self.tcp_sock, f"HASH {filename}")
            if res.startswith("200"):
                server_hash = res.split(' ')[1].strip()
                hasher = hashlib.sha256()
                with open(local_path, "rb") as f:
                    hasher.update(f.read())
                local_hash = hasher.hexdigest()
                
                msg = f"Server SHA-256: {server_hash}\nLocal SHA-256:  {local_hash}\n\n"
                if server_hash.lower() == local_hash.lower():
                    msg += "KẾT QUẢ: File toàn vẹn tuyệt đối (MATCH)!"
                    messagebox.showinfo("Kết quả Hash Check", msg)
                    self.write_log("Kiểm tra HASH: Khớp hoàn toàn (Match)")
                else:
                    msg += "KẾT QUẢ: File bị lệch hoặc hư hại (MISMATCH)!"
                    messagebox.showerror("Kết quả Hash Check", msg)
                    self.write_log("Kiểm tra HASH: Không khớp (Mismatch)")
            else:
                self.write_log("Lỗi từ Server khi yêu cầu HASH.")
        threading.Thread(target=_task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientGUI(root)
    
    # In thử 2 dòng log mồi để em xem hiệu ứng
    app.write_log("Khởi động Hybrid FTP Client...")
    app.write_log("220 Chon Hybrid FTP Server xin chao", is_client=False)
    
    root.mainloop()