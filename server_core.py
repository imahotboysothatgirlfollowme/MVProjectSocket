import socket
import threading
import os
from ftp_commands import FTPCommandProcessor

HOST = '0.0.0.0'
PORT = 2121
SERVER_ROOT = os.path.abspath(os.getcwd())

# Dictionary chứa trạng thái toàn cầu của các client
active_clients = {}

class FTPServerCore:
    def __init__(self, write_log_callback, update_dashboard_callback):
        self.write_log = write_log_callback
        self.update_dashboard = update_dashboard_callback

    def start(self):
        """Hàm chạy Server (sẽ được nhúng vào luồng phụ để không treo GUI)"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((HOST, PORT))
        server.listen(5)
        self.write_log(f"[+] LÕI TCP ĐANG LẮNG NGHE TẠI {HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_client_thread, args=(conn, addr), daemon=True).start()

    def handle_client_thread(self, conn, addr):
        """Luồng chuyên biệt xử lý riêng cho từng Client"""
        self.write_log(f"[+] Có Client kết nối từ {addr}")
        conn.sendall(b"220 Chon Hybrid FTP Server xin chao\r\n")

        # Khởi tạo trạng thái cho Client mới
        active_clients[addr] = {
            "user": "Chưa rõ", "status": "Đang chờ đăng nhập", 
            "mode": "-", "data_type": "I", "tran_mode": "S",
            "current_dir": SERVER_ROOT
        }
        self.update_dashboard()

        # Gọi "chuyên gia" xử lý nghiệp vụ FTP từ file ftp_commands.py
        processor = FTPCommandProcessor(conn, addr, SERVER_ROOT, active_clients, self.write_log, self.update_dashboard)

        try:
            while True:
                data = conn.recv(1024).decode('utf-8').strip()
                if not data: break
                
                self.write_log(f"[{addr[1]}] Client ra lệnh: {data}")
                
                # Ném lệnh cho processor xử lý. Nếu nó trả về False (Lệnh QUIT), thì thoát vòng lặp.
                keep_alive = processor.process(data)
                if not keep_alive:
                    break
                    
        except ConnectionResetError:
            self.write_log(f"[!] Client {addr} ngắt kết nối đột ngột.")
        finally:
            if processor.pasv_sock: processor.pasv_sock.close()
            conn.close()
            if addr in active_clients:
                del active_clients[addr]
            self.write_log(f"[-] Client {addr} đã thoát.")
            self.update_dashboard()