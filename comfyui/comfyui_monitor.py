import requests
import json
import time
import datetime
import logging
from threading import Thread
import os
import colorama
from colorama import Fore, Style, Back

# 初始化colorama
colorama.init()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("comfyui_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ComfyUIMonitor")

class ComfyUIMonitor:
    def __init__(self, api_url="http://localhost:8888", poll_interval=2):
        self.api_url = api_url.rstrip("/")
        self.poll_interval = poll_interval
        self.known_prompts = set()  # 记录已知的prompt IDs
        self.running = False
        self.thread = None
    
    def start(self):
        """启动监控线程"""
        if self.running:
            logger.warning("监控器已经在运行中")
            return
        
        self.running = True
        self.thread = Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"开始监控 ComfyUI 任务 (API URL: {self.api_url})")
    
    def stop(self):
        """停止监控线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
            logger.info("监控器已停止")
    
    def get_history(self):
        """获取历史记录"""
        try:
            response = requests.get(f"{self.api_url}/history", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                logger.error(f"获取历史记录失败: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"获取历史记录错误: {str(e)}")
            return None
    
    def _monitor_loop(self):
        """监控主循环"""
        while self.running:
            try:
                # 获取历史记录
                history = self.get_history()
                if not history:
                    time.sleep(self.poll_interval)
                    continue
                
                # 处理历史记录中的每个prompt
                for prompt_id, data in history.items():
                    # 检查是否是新完成的任务
                    if prompt_id not in self.known_prompts:
                        # 检查任务是否已完成
                        if "status" in data:
                            status_data = data["status"]
                            
                            if isinstance(status_data, dict) and "completed" in status_data and status_data["completed"]:
                                logger.info(f"检测到新完成的任务: {prompt_id}")
                                self.known_prompts.add(prompt_id)
                                self.handle_completed_task(prompt_id, data)
            
            except Exception as e:
                logger.error(f"监控循环错误: {str(e)}")
            
            time.sleep(self.poll_interval)
    
    def handle_completed_task(self, prompt_id, data):
        """处理已完成的任务"""
        try:
            logger.info(f"任务 {prompt_id} 已完成")
            
            # 提取输出文件和其他信息
            output_files = []
            node_outputs = {}
            
            if "outputs" in data:
                outputs = data["outputs"]
                for node_id, node_output in outputs.items():
                    # 检查是否有图像输出
                    if "images" in node_output:
                        images = node_output["images"]
                        node_files = []
                        for img in images:
                            if "filename" in img:
                                filename = img["filename"]
                                full_path = self.get_output_path(filename)
                                logger.info(f"生成图像: {filename}")
                                node_files.append(filename)
                                output_files.append(filename)
                                # 调用图像回调
                                self.on_image_generated(prompt_id, node_id, filename, full_path)
                        
                        if node_files:
                            node_outputs[node_id] = node_files
                    
                    # 处理其他类型的输出
                    for output_key, output_value in node_output.items():
                        if output_key != "images":
                            if node_id not in node_outputs:
                                node_outputs[node_id] = {}
                            if isinstance(node_outputs[node_id], list):
                                # 转换为字典
                                files = node_outputs[node_id]
                                node_outputs[node_id] = {"images": files}
                            
                            node_outputs[node_id][output_key] = output_value
            
            # 获取状态信息
            status_info = {}
            if "status" in data and isinstance(data["status"], dict):
                status_data = data["status"]
                status_info["status"] = status_data.get("status_str", "unknown")
                
                # 提取执行时间
                execution_time = None
                if "messages" in status_data:
                    messages = status_data["messages"]
                    start_time = None
                    end_time = None
                    
                    for msg in messages:
                        if len(msg) >= 2 and isinstance(msg[1], dict) and "timestamp" in msg[1]:
                            if msg[0] == "execution_start":
                                start_time = msg[1]["timestamp"]
                            elif msg[0] == "execution_success":
                                end_time = msg[1]["timestamp"]
                    
                    if start_time and end_time:
                        execution_time = (end_time - start_time) / 1000  # 转换为秒
                        status_info["execution_time"] = execution_time
            
            # 调用完成回调
            self.on_task_completed(prompt_id, data, output_files, node_outputs, status_info)
            
        except Exception as e:
            logger.error(f"处理完成任务时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_output_path(self, filename):
        """获取输出文件的完整路径"""
        # 此方法可根据您的实际安装路径相应调整
        base_dirs = [
            os.path.join(os.getcwd(), "output"),
            os.path.join(os.getcwd(), "ComfyUI", "output"),
            "/output"
        ]
        
        for base_dir in base_dirs:
            path = os.path.join(base_dir, filename)
            if os.path.exists(path):
                return path
        
        # 如果找不到文件，返回基于当前目录的猜测路径
        return os.path.join(os.getcwd(), "output", filename)
    
    def on_image_generated(self, prompt_id, node_id, filename, filepath):
        """图像生成回调 - 可以被子类覆盖"""
        # 这是一个可以被子类覆盖的方法
        pass
    
    def on_task_completed(self, prompt_id, data, output_files, node_outputs, status_info):
        """任务完成回调 - 可以被子类覆盖"""
        # 这是一个可以被子类覆盖的方法
        pass

# 实现自定义监控器
class PrettyComfyUIMonitor(ComfyUIMonitor):
    def __init__(self, api_url="http://localhost:8888", poll_interval=2):
        super().__init__(api_url, poll_interval)
        # 计数器用于任务序号
        self.task_counter = 0
        # 终端宽度
        self.term_width = self._get_terminal_width()
    
    def _get_terminal_width(self):
        """获取终端宽度"""
        try:
            return os.get_terminal_size().columns
        except:
            return 80  # 默认值
    
    def on_image_generated(self, prompt_id, node_id, filename, filepath):
        """重写图像生成回调"""
        # 不打印日志，由任务完成时统一显示
        pass
    
    def on_task_completed(self, prompt_id, data, output_files, node_outputs, status_info):
        """重写任务完成回调，使用美化格式显示"""
        self.task_counter += 1
        self.term_width = self._get_terminal_width()
        
        # 顶部边框
        self._print_header(f"任务 #{self.task_counter} 已完成")
        
        # 任务ID
        shortened_id = prompt_id[:8] + "..." + prompt_id[-8:] if len(prompt_id) > 20 else prompt_id
        print(f"{Fore.CYAN}任务ID:{Style.RESET_ALL} {shortened_id}")
        
        # 状态信息
        status = status_info.get("status", "未知")
        status_color = Fore.GREEN if status == "success" else Fore.RED
        print(f"{Fore.CYAN}状态:{Style.RESET_ALL} {status_color}{status}{Style.RESET_ALL}")
        
        # 执行时间
        if "execution_time" in status_info:
            print(f"{Fore.CYAN}执行时间:{Style.RESET_ALL} {status_info['execution_time']:.2f} 秒")
        
        # 生成的文件
        if output_files:
            print(f"\n{Fore.YELLOW}生成的文件:{Style.RESET_ALL}")
            for i, file in enumerate(output_files):
                print(f"  {i+1}. {file}")
        
        # 节点输出详情
        if node_outputs and len(node_outputs) > 0:
            print(f"\n{Fore.YELLOW}节点输出详情:{Style.RESET_ALL}")
            for node_id, outputs in node_outputs.items():
                print(f"  {Fore.CYAN}节点 {node_id}:{Style.RESET_ALL}")
                
                if isinstance(outputs, list):
                    # 图像列表
                    for img in outputs:
                        print(f"    - {img}")
                elif isinstance(outputs, dict):
                    # 混合输出
                    for key, value in outputs.items():
                        if key == "images" and isinstance(value, list):
                            print(f"    - 图像: {', '.join(value)}")
                        else:
                            # 处理其他类型的输出，如文本、数值等
                            if isinstance(value, list) and len(value) <= 3:
                                val_str = str(value)
                            elif isinstance(value, list):
                                val_str = f"[列表，{len(value)}项]"
                            else:
                                val_str = str(value)
                            print(f"    - {key}: {val_str}")
        
        # 系统消息
        if "status" in data and isinstance(data["status"], dict) and "messages" in data["status"]:
            messages = data["status"]["messages"]
            if messages and len(messages) > 0:
                print(f"\n{Fore.YELLOW}系统消息:{Style.RESET_ALL}")
                for msg in messages:
                    if len(msg) >= 2:
                        msg_type = msg[0]
                        msg_data = msg[1]
                        
                        # 格式化时间戳
                        ts = ""
                        if isinstance(msg_data, dict) and "timestamp" in msg_data:
                            try:
                                dt = datetime.datetime.fromtimestamp(msg_data["timestamp"]/1000)
                                ts = dt.strftime("%H:%M:%S")
                            except:
                                ts = str(msg_data["timestamp"])
                        
                        print(f"  - {Fore.CYAN}{msg_type}{Style.RESET_ALL}: {ts}")
        
        # 底部边框
        self._print_footer()
        
        # 可以在这里调用您的自定义回调API
        # self.call_your_backend_api(prompt_id, output_files, status)
    
    def _print_header(self, title):
        """打印美化的标题栏"""
        width = min(self.term_width, 100)
        title_len = len(title)
        padding = max(2, (width - title_len - 4) // 2)
        
        border = "═" * width
        print(f"\n{Fore.BLUE}╔{border}╗{Style.RESET_ALL}")
        print(f"{Fore.BLUE}║{' ' * padding}{Fore.YELLOW}{title}{Fore.BLUE}{' ' * (width - padding - title_len - 2)}║{Style.RESET_ALL}")
        print(f"{Fore.BLUE}╠{border}╣{Style.RESET_ALL}")
    
    def _print_footer(self):
        """打印美化的底部"""
        width = min(self.term_width, 100)
        border = "═" * width
        print(f"{Fore.BLUE}╚{border}╝{Style.RESET_ALL}")
        print()  # 空行分隔

# 主函数
if __name__ == "__main__":
    import sys
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="ComfyUI 任务监控器")
    parser.add_argument("--url", default="http://localhost:8888", help="ComfyUI API URL")
    parser.add_argument("--interval", type=float, default=2, help="轮询间隔(秒)")
    args = parser.parse_args()
    
    # 创建并启动监控器
    monitor = PrettyComfyUIMonitor(api_url=args.url, poll_interval=args.interval)
    
    try:
        # 清屏
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # 显示欢迎信息
        print(f"{Fore.GREEN}╔═══════════════════════════════════════════════╗{Style.RESET_ALL}")
        print(f"{Fore.GREEN}║                                               ║{Style.RESET_ALL}")
        print(f"{Fore.GREEN}║{Fore.YELLOW}        ComfyUI 任务监控器已启动         {Fore.GREEN}║{Style.RESET_ALL}")
        print(f"{Fore.GREEN}║                                               ║{Style.RESET_ALL}")
        print(f"{Fore.GREEN}╚═══════════════════════════════════════════════╝{Style.RESET_ALL}")
        print(f"正在监控 ComfyUI 任务... ({args.url})")
        print(f"轮询间隔: {args.interval} 秒")
        print("按 Ctrl+C 终止")
        print()
        
        # 开始监控
        monitor.start()
        
        # 保持主线程运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}收到终止信号{Style.RESET_ALL}")
        monitor.stop()
    except Exception as e:
        print(f"\n{Fore.RED}发生错误: {str(e)}{Style.RESET_ALL}")
        monitor.stop()