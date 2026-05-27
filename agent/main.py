"""美团本地活动规划 Agent - CLI 交互入口

支持的命令：
  - 直接输入自然语言 → Agent 分析并规划活动
  - /偏好 [内容]     → 设置或查看用户偏好
  - /reset           → 重置对话状态
  - /help            → 显示帮助信息
  - /quit            → 退出程序
"""
import sys
import os

# 将项目根目录加入 sys.path，确保子模块可以互相 import
sys.path.insert(0, os.path.dirname(__file__))

from agent.core import Agent


# 程序启动时显示的欢迎信息
BANNER = """
╔══════════════════════════════════════════════════╗
║     美团本地活动规划 Agent                        ║
║     把事情做完，不只是搜索                        ║
╚══════════════════════════════════════════════════╝

输入示例：
  📌 规划："今天下午想带5岁的孩子出去玩"
  📌 规划："4个人，2男2女，想出去玩几个小时"
  📌 偏好：/偏好 我喜欢吃火锅，不喜欢吃辣
  📌 查看偏好：/偏好
  📌 重置对话：/reset
  📌 退出：/quit

提示：
  - 规划过程中可以随时加入新信息（如"对了，我老婆在减肥"）
  - 确认方案后回复"确认"即可一键下单
"""


def main():
    """CLI 主循环"""
    print(BANNER)

    # 初始化 Agent 实例（整个会话共享同一个 Agent）
    agent = Agent()

    while True:
        try:
            user_input = input("\n💬 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C 或管道输入结束时优雅退出
            print("\n再见！")
            break

        # 跳过空输入
        if not user_input:
            continue

        # ===== 特殊命令处理 =====
        if user_input in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        if user_input == "/reset":
            agent.reset()
            print("🔄 对话已重置")
            continue

        if user_input == "/偏好":
            # 查看当前偏好
            prefs = agent.get_preferences()
            print(f"\n📋 当前偏好设置：\n{prefs}")
            continue

        if user_input.startswith("/偏好 "):
            # 设置偏好：去掉命令前缀，作为偏好设置消息传给 Agent
            pref_input = user_input[4:].strip()
            response = agent.chat(f"设置偏好：{pref_input}")
            print(f"\n🤖 助手: {response}")
            continue

        if user_input == "/help":
            print(BANNER)
            continue

        # ===== 正常对话：交给 Agent 处理 =====
        response = agent.chat(user_input)
        print(f"\n🤖 助手: {response}")


if __name__ == "__main__":
    main()
