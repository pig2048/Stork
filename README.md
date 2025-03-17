# Stork Auto Bot

Stork Auto Bot 是一个自动化工具，用于与 Stork Oracle 网络进行交互，执行价格验证等任务。它支持多账户管理、代理请求和实时状态显示，旨在简化与 Stork Oracle 的集成。

## 功能

- **自动价格验证**：定期从 Stork Oracle 获取价格数据并进行验证。
- **多账户支持**：通过 `accounts.py` 文件管理多个账户。
- **代理支持**：通过 `proxies.txt` 配置代理以增强网络请求的灵活性。
- **实时监控**：显示用户统计信息、验证状态和价格数据。
- **日志记录**：将操作日志保存到 `stork_bot.log` 文件中。

## 安装

按照以下步骤设置和运行项目：

1. **克隆仓库到本地：**
   ```bash
   git clone https://github.com/pig2048/Stork.git
   cd Stork
   ```

2. **创建并激活虚拟环境：**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **安装依赖：**
    ```bash
    pip install -r requirements.txt
    ```
4. **配置 accounts.py 文件：**
    - **将你注册后的邮箱和密码填入**

5. **配置代理(可选):**
    - **在 proxies.txt 文件中添加代理地址，每行一个。**
    - 示例：
    ```bash
    http://proxy1:port
    http://proxy2:port
    ```
## 运行脚本
    ```bash
    python main.py
    ```
