'use client';

import { useState, useEffect, useRef } from 'react';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AgentLog {
  id: number;
  type: 'thinking' | 'status' | 'skill_detected' | 'plan_created' | 'error' | 'preferences';
  content: string;
  timestamp: Date;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentLogs, setAgentLogs] = useState<AgentLog[]>([]);
  const [input, setInput] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentPlanId, setCurrentPlanId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const messageIdRef = useRef(0);
  const logIdRef = useRef(0);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, agentLogs]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/chat');

    ws.onopen = () => {
      setIsConnected(true);
      addLog('status', '已连接到服务器');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          addLog('status', data.content);
          break;

        case 'thinking':
          addLog('thinking', data.content);
          break;

        case 'skill_detected':
          addLog('skill_detected', data.content);
          break;

        case 'plan_created':
          addLog('plan_created', data.content);
          break;

        case 'preferences':
          addLog('preferences', data.content);
          break;

        case 'chunk':
          setMessages(prev => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
              return [
                ...prev.slice(0, -1),
                { ...lastMsg, content: lastMsg.content + data.content }
              ];
            }
            return [...prev, {
              id: messageIdRef.current++,
              role: 'assistant',
              content: data.content,
              timestamp: new Date()
            }];
          });
          break;

        case 'ai_message':
          addLog('thinking', 'AI正在思考...');
          break;

        case 'skill_result':
          setMessages(prev => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
              return [
                ...prev.slice(0, -1),
                { ...lastMsg, content: lastMsg.content + '\n' + data.content }
              ];
            }
            return [...prev, {
              id: messageIdRef.current++,
              role: 'assistant',
              content: data.content,
              timestamp: new Date()
            }];
          });
          break;

        case 'done':
          setIsProcessing(false);
          if (data.plan_id) {
            setCurrentPlanId(data.plan_id);
          }
          break;

        case 'error':
          addLog('error', data.content);
          setIsProcessing(false);
          break;
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      addLog('status', '连接已断开');
    };

    ws.onerror = () => {
      addLog('error', '连接错误');
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, []);

  const addLog = (type: AgentLog['type'], content: string) => {
    setAgentLogs(prev => [...prev, {
      id: logIdRef.current++,
      type,
      content,
      timestamp: new Date()
    }]);
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !wsRef.current || isProcessing) return;

    const userMessage = input.trim();
    setInput('');

    setMessages(prev => [...prev, {
      id: messageIdRef.current++,
      role: 'user',
      content: userMessage,
      timestamp: new Date()
    }]);

    setIsProcessing(true);
    wsRef.current.send(JSON.stringify({ type: 'message', content: userMessage }));
  };

  const getLogIcon = (type: AgentLog['type']) => {
    switch (type) {
      case 'thinking': return '🤔';
      case 'status': return '📡';
      case 'skill_detected': return '⚡';
      case 'plan_created': return '📋';
      case 'preferences': return '⚙️';
      case 'error': return '❌';
    }
  };

  const getLogColor = (type: AgentLog['type']) => {
    switch (type) {
      case 'thinking': return 'text-blue-600';
      case 'status': return 'text-gray-600';
      case 'skill_detected': return 'text-purple-600';
      case 'plan_created': return 'text-green-600';
      case 'preferences': return 'text-orange-600';
      case 'error': return 'text-red-600';
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">Agent 思考过程</h2>
          <div className="flex items-center gap-2 mt-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-sm text-gray-500">
              {isConnected ? '已连接' : '未连接'}
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {agentLogs.length === 0 ? (
            <div className="text-center text-gray-400 py-8">
              <p className="text-sm">等待Agent响应...</p>
              <p className="text-xs mt-2 text-gray-300">提示：可以直接告诉小团你的偏好，比如"我有个5岁的孩子"</p>
            </div>
          ) : (
            agentLogs.map(log => (
              <div key={log.id} className="flex items-start gap-2">
                <span className="text-lg">{getLogIcon(log.type)}</span>
                <div className="flex-1">
                  <p className={`text-sm ${getLogColor(log.type)}`}>{log.content}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {log.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>

        <div className="p-4 border-t border-gray-200 text-center">
          <p className="text-xs text-gray-400">
            💡 直接在对话中告诉小团你的偏好
          </p>
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        <header className="bg-white border-b border-gray-200 px-6 py-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-meituan-yellow rounded-full flex items-center justify-center">
                <span className="text-xl">🎯</span>
              </div>
              <div>
                <h1 className="text-xl font-semibold text-gray-800">活动规划助手</h1>
                <p className="text-sm text-gray-500">
                  {currentPlanId ? `当前方案: ${currentPlanId}` : '智能规划您的活动'}
                </p>
              </div>
            </div>
            {isProcessing && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <div className="animate-spin w-4 h-4 border-2 border-meituan-yellow border-t-transparent rounded-full"></div>
                处理中...
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-20 h-20 bg-meituan-yellow rounded-full flex items-center justify-center mx-auto mb-6">
                  <span className="text-4xl">👋</span>
                </div>
                <h2 className="text-2xl font-semibold text-gray-700 mb-3">欢迎使用活动规划助手</h2>
                <p className="text-gray-500 mb-6">告诉我您的需求，我来帮您规划完美的活动方案</p>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="p-4 bg-white rounded-lg border border-gray-200">
                    <span className="text-2xl mb-2 block">👨‍👩‍👧</span>
                    <p className="text-gray-600">亲子出行</p>
                  </div>
                  <div className="p-4 bg-white rounded-lg border border-gray-200">
                    <span className="text-2xl mb-2 block">👥</span>
                    <p className="text-gray-600">朋友聚会</p>
                  </div>
                  <div className="p-4 bg-white rounded-lg border border-gray-200">
                    <span className="text-2xl mb-2 block">💑</span>
                    <p className="text-gray-600">约会安排</p>
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-6">也可以告诉我您的偏好，比如："我有个5岁的孩子，老婆在减肥"</p>
              </div>
            ) : (
              messages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] px-4 py-3 rounded-2xl ${
                      msg.role === 'user'
                        ? 'bg-meituan-yellow text-gray-800'
                        : 'bg-white text-gray-800 border border-gray-200'
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                    <div className={`text-xs mt-2 ${
                      msg.role === 'user' ? 'text-gray-600' : 'text-gray-400'
                    }`}>
                      {msg.timestamp.toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="bg-white border-t border-gray-200 p-4">
          <form onSubmit={sendMessage} className="max-w-3xl mx-auto flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isProcessing ? "Agent正在处理中..." : "输入您的需求，随时可以补充信息..."}
              disabled={isProcessing}
              className="flex-1 px-4 py-3 bg-gray-100 rounded-xl border-2 border-transparent focus:border-meituan-yellow focus:bg-white focus:outline-none transition-all disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || isProcessing}
              className="px-6 py-3 bg-meituan-yellow text-gray-800 rounded-xl hover:opacity-90 transition-opacity font-medium disabled:opacity-50"
            >
              发送
            </button>
          </form>
        </footer>
      </div>
    </div>
  );
}
