"""调试测试脚本"""
import sys
import os
sys.path.insert(0, '.')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from agent.core import Agent

def debug_test():
    """Debug the agent flow"""
    agent = Agent()

    print("=" * 60)
    print("Debug: User says '给我规划一下晚饭'")
    print("=" * 60)

    # Store initial state
    print("\nInitial state:")
    print(f"  step: {agent.state.get('step')}")
    print(f"  plan: {agent.state.get('plan')}")

    # Call chat
    response = agent.chat("给我规划一下晚饭")

    print("\nAfter calling chat():")
    print(f"  response length: {len(response)} chars")
    print(f"  response preview: {response[:100]}...")
    print(f"  state step: {agent.state.get('step')}")
    print(f"  state plan keys: {list(agent.state.get('plan', {}).keys())}")
    print(f"  state plan exists: {bool(agent.state.get('plan'))}")

    # Check the full response
    print("\n" + "=" * 60)
    print("Full Response:")
    print("=" * 60)
    print(response)

if __name__ == "__main__":
    debug_test()
