'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import MatrixView from './MatrixView';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AgentLog {
  id: number;
  type: 'thinking' | 'status' | 'skill_detected' | 'plan_created' | 'error' | 'preferences' | 'plan_updated';
  content: string;
  skillId?: string;
  timestamp: Date;
}

interface TimeSlot {
  start: string;
  end: string;
}

interface Location {
  lat: number;
  lng: number;
  address?: string;
  name?: string;
}

interface PreBook {
  need: boolean;
  type: string;
  item: string;
}

interface ActivityDetails {
  rating?: number;
  price?: number;
  tags?: string[];
  description?: string;
}

interface PlanActivity {
  order: number;
  time_slot: TimeSlot;
  activity_type: string;
  name: string;
  item_id?: string;
  location?: Location;
  duration_hours?: number;
  duration_minutes?: number;
  distance_m?: number;
  mode?: string;
  mode_label?: string;
  mode_icon?: string;
  from_location?: Location;
  to_location?: Location;
  details?: ActivityDetails;
  pre_book?: PreBook;
  notes?: string;
}

interface DagNode {
  id: string;
  type: 'activity' | 'alternative';
  activity_index: number;
  alternative_index?: number;
  is_original: boolean;
  activity: PlanActivity;
  llm_score?: number;
}

interface DagEdge {
  from: string;
  to: string;
  transport?: {
    mode: string;
    mode_label: string;
    duration_minutes: number;
    distance_m: number;
  };
}

interface Dag {
  plan_id: string;
  nodes: DagNode[];
  edges: DagEdge[];
  recommended_path: string[];
}

interface ActivityAlternatives {
  [key: number]: DagNode[];
}

interface OrderedItems {
  [key: number]: boolean;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentLogs, setAgentLogs] = useState<AgentLog[]>([]);
  const [input, setInput] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<PlanActivity[]>([]);
  const [currentPlanId, setCurrentPlanId] = useState<string>('');
  const [showPlanPanel, setShowPlanPanel] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastError, setLastError] = useState<{ code: string; message: string; retry: boolean } | null>(null);

  // Top-K 替代方案
  const [dag, setDag] = useState<Dag | null>(null);
  const [activityAlternatives, setActivityAlternatives] = useState<ActivityAlternatives>({});
  const [selectedNodeIds, setSelectedNodeIds] = useState<{ [key: number]: string }>({});
  const [isLoadingAlternatives, setIsLoadingAlternatives] = useState(false);
  const [switchingAltIndex, setSwitchingAltIndex] = useState<number | null>(null);  // 正在切换的替代方案索引
  const [transportAltIndices, setTransportAltIndices] = useState<{ [key: number]: number }>({});  // 交通替代方案索引

  // 下单相关
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [selectedItems, setSelectedItems] = useState<OrderedItems>({});
  const [orderedItems, setOrderedItems] = useState<OrderedItems>({});
  const [bookingData, setBookingData] = useState({
    user_name: '',
    phone: '',
    date: new Date().toISOString().split('T')[0],
    people: 2,
  });
  const [bookingFormError, setBookingFormError] = useState<string>('');
  const [bookingFieldErrors, setBookingFieldErrors] = useState<{[key: string]: string}>({});
  const [bookingResult, setBookingResult] = useState<{success: boolean; message: string; details?: string; orders?: any[]} | null>(null);
  const [isBookingLoading, setIsBookingLoading] = useState(false);

  // 倒计时重试
  const [retryCountdown, setRetryCountdown] = useState<number>(0);
  const [retryMessage, setRetryMessage] = useState<string>('');
  const countdownRef = useRef<NodeJS.Timeout | null>(null);

  // 矩阵视图
  const [showMatrixView, setShowMatrixView] = useState(false);

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
  }, [messages, agentLogs, streamingContent]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/chat');

    ws.onopen = () => {
      setIsConnected(true);
      addLog('status', '已连接到服务器');
      setLastError(null);
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
          addLog('skill_detected', data.content, data.skill_id);
          break;

        case 'plan_created':
          addLog('plan_created', data.content);
          break;

        case 'plan_updated':
          addLog('plan_updated', '方案已更新');
          if (data.content) {
            setCurrentPlan(data.content as PlanActivity[]);
            if (data.plan_id) setCurrentPlanId(data.plan_id);
            setTransportAltIndices({});
          }
          break;

        case 'preference_update':
          addLog('preferences', data.content);
          break;

        case 'chunk':
          setIsStreaming(true);
          setStreamingContent(prev => prev + data.content);
          break;

        case 'ai_message':
          setIsStreaming(false);
          setStreamingContent('');
          setMessages(prev => [...prev, {
            id: messageIdRef.current++,
            role: 'assistant',
            content: data.content,
            timestamp: new Date()
          }]);
          break;

        case 'plan':
          if (data.content && data.content.length > 0) {
            setCurrentPlan(data.content as PlanActivity[]);
            if (data.plan_id) setCurrentPlanId(data.plan_id);
            setShowPlanPanel(true);
            // 清空替代方案和已下单状态
            setDag(null);
            setActivityAlternatives({});
            setSelectedNodeIds({});
            setOrderedItems({});
            setSelectedItems({});
            setTransportAltIndices({});
          }
          break;

        case 'done':
          setIsProcessing(false);
          setIsStreaming(false);
          setStreamingContent('');
          setLastError(null);
          // 清除倒计时
          setRetryCountdown(0);
          if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
          if (data.plan && data.plan.length > 0) {
            setCurrentPlan(data.plan as PlanActivity[]);
            if (data.plan_id) setCurrentPlanId(data.plan_id);
            setShowPlanPanel(true);
            setTransportAltIndices({});
          }
          break;

        case 'plan_validation_failed':
          // JSON 校验失败 → 显示倒计时重试UI
          const cd = data.countdown || 3;
          const msg = data.message || '方案解析异常，即将自动重新生成...';
          setRetryCountdown(cd);
          setRetryMessage(msg);
          addLog('error', msg);
          // 清除旧计时器
          if (countdownRef.current) clearInterval(countdownRef.current);
          countdownRef.current = setInterval(() => {
            setRetryCountdown(prev => {
              if (prev <= 1) {
                if (countdownRef.current) clearInterval(countdownRef.current);
                // 自动发送重试
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                  wsRef.current.send(JSON.stringify({ type: 'retry_planner' }));
                }
                return 0;
              }
              return prev - 1;
            });
          }, 1000);
          break;

        case 'error':
          setLastError({
            code: data.code,
            message: data.message,
            retry: data.retry || false,
          });
          addLog('error', `${data.code}: ${data.message}`);
          setIsProcessing(false);
          setIsStreaming(false);
          setStreamingContent('');
          break;

        default:
          console.log('未知消息类型:', data);
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
      if (countdownRef.current) clearInterval(countdownRef.current);
      ws.close();
    };
  }, []);

  // 监听矩阵视图返回的结果
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const { plan: resultPlan, planId: resultPlanId } = e.detail;
      if (resultPlan) {
        setCurrentPlan(resultPlan);
        if (resultPlanId) setCurrentPlanId(resultPlanId);
        setShowPlanPanel(true);
        setShowMatrixView(false);
        addLog('plan_updated', '已应用矩阵路径方案');
        // 重置替代方案相关状态
        setDag(null);
        setActivityAlternatives({});
        setSelectedNodeIds({});
        setTransportAltIndices({});
      }
    };
    window.addEventListener('matrix_result', handler as EventListener);
    return () => window.removeEventListener('matrix_result', handler as EventListener);
  }, []);

  const addLog = (type: AgentLog['type'], content: string, skillId?: string) => {
    setAgentLogs(prev => [...prev, {
      id: logIdRef.current++,
      type,
      content,
      skillId,
      timestamp: new Date()
    }]);
  };

  const sendMessage = async (e: React.FormEvent, messageType: 'message' | 'interrupt' = 'message') => {
    e.preventDefault();
    if (!input.trim() || !wsRef.current) return;

    const userMessage = input.trim();
    setInput('');

    setMessages(prev => [...prev, {
      id: messageIdRef.current++,
      role: 'user',
      content: userMessage,
      timestamp: new Date()
    }]);

    if (messageType === 'message') {
      setIsProcessing(true);
      setLastError(null);
    }
    wsRef.current.send(JSON.stringify({ type: messageType, content: userMessage }));
  };

  const sendRetry = () => {
    if (!wsRef.current) return;
    setIsProcessing(true);
    setLastError(null);
    wsRef.current.send(JSON.stringify({ type: 'retry' }));
  };

  const sendRetryPlanner = () => {
    if (!wsRef.current) return;
    // 清除倒计时
    if (countdownRef.current) clearInterval(countdownRef.current);
    setRetryCountdown(0);
    setIsProcessing(true);
    wsRef.current.send(JSON.stringify({ type: 'retry_planner' }));
  };

  // ============== Top-K 替代方案 ==============

  const loadAlternatives = async () => {
    if (currentPlan.length === 0) return;
    setIsLoadingAlternatives(true);

    try {
      const response = await fetch('http://localhost:8000/api/plan/alternatives', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_id: currentPlanId,
          plan: currentPlan,
          top_k: 3,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const result = await response.json();
      setDag(result);

      // 按 activity_index 组织替代方案
      const grouped: ActivityAlternatives = {};
      const initialSelected: { [key: number]: string } = {};

      result.nodes.forEach((node: DagNode) => {
        const idx = node.activity_index;
        if (!grouped[idx]) grouped[idx] = [];
        grouped[idx].push(node);
        if (node.is_original) initialSelected[idx] = node.id;
      });

      setActivityAlternatives(grouped);
      setSelectedNodeIds(initialSelected);
    } catch (error: any) {
      console.error('加载替代方案失败:', error);
      alert(`加载替代方案失败: ${error?.message || error?.detail || '请检查网络连接'}`);
    } finally {
      setIsLoadingAlternatives(false);
    }
  };

  const selectAlternative = async (activityIndex: number, nodeId: string) => {
    const newSelected = { ...selectedNodeIds, [activityIndex]: nodeId };
    setSelectedNodeIds(newSelected);
    setSwitchingAltIndex(activityIndex);

    if (!dag) {
      setSwitchingAltIndex(null);
      return;
    }

    // 构造新的 selected_nodes 序列
    const sortedIndexes = Object.keys(newSelected).map(Number).sort((a, b) => a - b);
    const selected_nodes: string[] = sortedIndexes.map(idx => newSelected[idx]);

    setIsProcessing(true);
    try {
      const response = await fetch('http://localhost:8000/api/plan/reroute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_id: currentPlanId,
          selected_nodes,
          all_nodes: dag.nodes,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const result = await response.json();
      if (result.plan) {
        setCurrentPlan(result.plan);
        addLog('plan_updated', `已切换到「${result.plan.find((a: PlanActivity) =>
          a.activity_type !== 'transport' &&
          a.name === dag.nodes.find(n => n.id === nodeId)?.activity?.name
        )?.name || '替代方案'}」`);
      } else {
        throw new Error('返回数据不包含 plan');
      }
    } catch (error: any) {
      console.error('重规划失败:', error);
      addLog('error', `切换方案失败: ${error?.message || '请重试'}`);
    } finally {
      setIsProcessing(false);
      setSwitchingAltIndex(null);
    }
  };

  // 切换交通模式
  const cycleTransportMode = (planIndex: number, direction: 'prev' | 'next') => {
    const activity = currentPlan[planIndex];
    if (activity.activity_type !== 'transport') return;
    if (!activity.from_location || !activity.to_location) return;

    const modes = ['walking', 'taxi', 'public_transit', 'driving'] as const;
    const modeLabels: Record<string, string> = { walking: '步行', taxi: '打车', public_transit: '公共交通', driving: '自驾' };
    const modeIcons: Record<string, string> = { walking: '🚶', taxi: '🚕', public_transit: '🚌', driving: '🚗' };
    const speeds: Record<string, number> = { walking: 5, taxi: 35, public_transit: 25, driving: 30 };
    const overheads: Record<string, number> = { walking: 0, taxi: 5, public_transit: 8, driving: 8 };

    const currentMode = activity.mode || 'taxi';
    const currentIdx = modes.indexOf(currentMode as any);
    const newIdx = direction === 'next'
      ? (currentIdx + 1) % modes.length
      : (currentIdx - 1 + modes.length) % modes.length;
    const newMode = modes[newIdx];

    // Haversine distance
    const lat1 = activity.from_location.lat;
    const lng1 = activity.from_location.lng;
    const lat2 = activity.to_location.lat;
    const lng2 = activity.to_location.lng;
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    const distanceM = R * c;
    const speed = speeds[newMode] || 35;
    const overhead = overheads[newMode] || 5;
    const durationMin = Math.max(1, Math.round(distanceM / 1000 / speed * 60) + overhead);

    const updated = [...currentPlan];
    updated[planIndex] = {
      ...activity,
      mode: newMode,
      mode_label: modeLabels[newMode],
      mode_icon: modeIcons[newMode],
      duration_minutes: durationMin,
      distance_m: Math.round(distanceM),
      name: `${modeLabels[newMode]}前往${activity.to_location?.name || '下一站'}`,
      details: { description: `${modeLabels[newMode]}${durationMin}分钟 (${(distanceM / 1000).toFixed(1)}km)` },
    };
    setCurrentPlan(updated);
    setTransportAltIndices(prev => ({ ...prev, [planIndex]: newIdx }));

    addLog('plan_updated', `交通方式切换为: ${modeLabels[newMode]} ${durationMin}分钟`);
  };

  // 获取某个活动的当前选中替代方案索引
  const getSelectedAlternativeIndex = (activityIndex: number): number => {
    const alternatives = activityAlternatives[activityIndex];
    if (!alternatives) return 0;
    const selectedId = selectedNodeIds[activityIndex];
    const idx = alternatives.findIndex(n => n.id === selectedId);
    return idx >= 0 ? idx : 0;
  };

  // ============== 下单相关 ==============

  const getBookableActivities = () => {
    return currentPlan
      .map((activity, index) => ({ activity, index }))
      .filter(({ activity }) =>
        activity.pre_book?.need && activity.activity_type !== 'transport'
      );
  };

  const toggleSelectItem = (planIndex: number) => {
    setSelectedItems(prev => ({
      ...prev,
      [planIndex]: !prev[planIndex]
    }));
  };

  const selectAllUnordered = () => {
    const bookable = getBookableActivities();
    const newSelected: OrderedItems = {};
    bookable.forEach(({ index }) => {
      if (!orderedItems[index]) newSelected[index] = true;
    });
    setSelectedItems(newSelected);
  };

  const validateBookingForm = () => {
    const errors: {[key: string]: string } = {};
    if (!bookingData.user_name || bookingData.user_name.trim().length < 2) {
      errors.user_name = '姓名至少2个字符';
    }
    const phoneRegex = /^1[3-9]\d{9}$/;
    if (!bookingData.phone || !phoneRegex.test(bookingData.phone.trim())) {
      errors.phone = '请输入正确的11位手机号';
    }
    if (!bookingData.date) {
      errors.date = '请选择日期';
    }
    if (!bookingData.people || bookingData.people < 1 || bookingData.people > 20) {
      errors.people = '人数应在1-20之间';
    }
    setBookingFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateOrders = async () => {
    if (!validateBookingForm()) return;

    const bookable = getBookableActivities();
    const selectedBookable = bookable.filter(({ index }) => selectedItems[index]);

    if (selectedBookable.length === 0) {
      setBookingFormError('请选择要预订的项目');
      return;
    }

    setIsBookingLoading(true);
    setBookingFormError('');
    setBookingResult(null);

    try {
      const response = await fetch('http://localhost:8000/api/orders/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_id: currentPlanId,
          plan: currentPlan,
          user_name: bookingData.user_name,
          phone: bookingData.phone,
          date: bookingData.date,
        }),
      });
      const result = await response.json();

      if (response.ok) {
        setBookingResult({
          success: true,
          message: `验证完成：${result.total_orders ?? selectedBookable.length}个项目可预订`,
          details: JSON.stringify(result, null, 2),
        });
      } else {
        setBookingResult({
          success: false,
          message: result.detail || '验证失败',
        });
      }
    } catch (error: any) {
      console.error('验证订单失败:', error);
      setBookingResult({
        success: false,
        message: '验证失败：网络或服务不可用',
        details: error.message || '请稍后重试',
      });
    } finally {
      setIsBookingLoading(false);
    }
  };

  const executeSelectedOrders = async () => {
    if (!validateBookingForm()) return;

    const bookable = getBookableActivities();
    const selectedBookable = bookable.filter(({ index }) => selectedItems[index]);

    if (selectedBookable.length === 0) {
      setBookingFormError('请选择要预订的项目');
      return;
    }

    setIsBookingLoading(true);
    setBookingFormError('');
    setBookingResult(null);

    // 逐个执行
    const results = [];
    for (const { index, activity } of selectedBookable) {
      try {
        const response = await fetch(`http://localhost:8000/api/orders/execute/${index}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_id: currentPlanId,
            plan: currentPlan,
            user_name: bookingData.user_name,
            phone: bookingData.phone,
            date: bookingData.date,
          }),
        });
        const result = await response.json();
        results.push({ name: activity.name, result });
        if (result.success) {
          setOrderedItems(prev => ({ ...prev, [index]: true }));
          setSelectedItems(prev => ({ ...prev, [index]: false }));
        }
      } catch (error: any) {
        console.error(`下单失败: ${activity.name}`, error);
        results.push({ name: activity.name, result: { success: false, message: error.message || '网络错误' } });
      }
    }

    const successCount = results.filter(r => r.result.success).length;
    setBookingResult({
      success: successCount === results.length,
      message: `下单完成: ${successCount}/${results.length} 成功`,
      orders: results,
    });
    setIsBookingLoading(false);
  };

  // ============== 渲染 ==============

  const getActivityIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'attraction': return '🏛️';
      case 'restaurant': return '🍽️';
      case 'cafe': return '☕';
      case 'shop': return '🛍️';
      case 'activity': return '🎯';
      case 'transport': return '🚕';
      default: return '📌';
    }
  };

  const getTransportIcon = (icon?: string, mode?: string) => {
    if (icon) return icon;
    switch (mode?.toLowerCase()) {
      case 'taxi': return '🚕';
      case 'subway': return '🚇';
      case 'bus': return '🚌';
      case 'walking': return '🚶';
      case 'driving': return '🚗';
      default: return '🚕';
    }
  };

  // 计算非交通活动的索引
  const getNonTransportActivityIndex = (planIndex: number): number => {
    let count = 0;
    for (let i = 0; i < planIndex; i++) {
      if (currentPlan[i].activity_type !== 'transport') count++;
    }
    return count;
  };

  const bookableActivities = getBookableActivities();
  const unorderedBookable = bookableActivities.filter(({ index }) => !orderedItems[index]);
  const hasAlternatives = Object.keys(activityAlternatives).length > 0;

  return (
    <div className="flex h-screen bg-gray-100">
      {/* 左侧：Agent 思考日志 */}
      <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
        <div className="h-20 px-4 flex items-center border-b border-gray-200">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">Agent 思考过程</h2>
            <div className="flex items-center gap-2 mt-1">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-xs text-gray-500">
                {isConnected ? '已连接' : '未连接'}
              </span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {agentLogs.length === 0 ? (
            <div className="text-center text-gray-400 py-8">
              <p className="text-sm">等待Agent响应...</p>
              <p className="text-xs mt-2 text-gray-300">提示：可以直接告诉小团你的偏好</p>
            </div>
          ) : (
            agentLogs.map(log => (
              <div key={log.id} className="flex items-start gap-2">
                <span className="text-lg">
                  {log.type === 'thinking' ? '🤔' :
                   log.type === 'status' ? '📡' :
                   log.type === 'skill_detected' ? '⚡' :
                   log.type === 'plan_created' ? '📋' :
                   log.type === 'plan_updated' ? '🔄' :
                   log.type === 'preferences' ? '⚙️' : '❌'}
                </span>
                <div className="flex-1">
                  <p className={`text-sm ${
                    log.type === 'error' ? 'text-red-600' :
                    log.type === 'skill_detected' ? 'text-purple-600' :
                    log.type === 'preferences' ? 'text-orange-600' :
                    log.type === 'plan_created' || log.type === 'plan_updated' ? 'text-green-600' :
                    'text-gray-600'
                  }`}>{log.content}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {log.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* 中间：对话区域 */}
      <div className="flex-1 flex flex-col">
        <header className="h-20 bg-white border-b border-gray-200 px-6 shadow-sm flex items-center">
          <div className="flex items-center justify-between w-full">
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
            <div className="flex items-center gap-3">
              {isProcessing && (
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <div className="animate-spin w-4 h-4 border-2 border-meituan-yellow border-t-transparent rounded-full"></div>
                  处理中...
                </div>
              )}
              {/* 矩阵视图按钮 */}
              {currentPlan.length > 0 && (
                <button
                  onClick={() => setShowMatrixView(true)}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white text-sm rounded-lg hover:from-indigo-600 hover:to-purple-700 transition-all flex items-center gap-2 shadow-md"
                  title="以二维矩阵方式查看和选择方案"
                >
                  🔗 矩阵视图
                </button>
              )}
              {/* 方案面板切换按钮 */}
              {currentPlan.length > 0 && (
                <button
                  onClick={() => setShowPlanPanel(!showPlanPanel)}
                  className={`px-4 py-2 text-white text-sm rounded-lg transition-all flex items-center gap-2 shadow-sm ${
                    showPlanPanel
                      ? 'bg-gray-500 hover:bg-gray-600'
                      : 'bg-blue-500 hover:bg-blue-600'
                  }`}
                >
                  {showPlanPanel ? '✕ 隐藏方案' : '📋 查看方案'}
                </button>
              )}
            </div>
          </div>
        </header>

        {/* 倒计时重试横幅 */}
        {retryCountdown > 0 && (
          <div className="bg-amber-50 border-b border-amber-300 px-6 py-4">
            <div className="flex items-center justify-between max-w-3xl mx-auto">
              <div className="flex items-center gap-3">
                <span className="text-2xl animate-pulse">⏳</span>
                <div>
                  <p className="text-amber-800 font-medium">{retryMessage}</p>
                  <p className="text-amber-600 text-sm mt-0.5">
                    将使用非流式结构化输出重新生成，确保方案格式正确
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-3xl font-bold text-amber-600 tabular-nums">
                  {retryCountdown}
                </span>
                <button
                  onClick={sendRetryPlanner}
                  className="px-5 py-2.5 bg-amber-500 text-white rounded-xl font-medium hover:bg-amber-600 transition-colors shadow-sm flex items-center gap-2"
                >
                  🔄 立即重试
                </button>
              </div>
            </div>
          </div>
        )}

        {lastError && (
          <div className="bg-red-50 border-b border-red-200 px-6 py-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-red-600 font-medium">{lastError.code}</span>
                <p className="text-red-500 text-sm mt-1">{lastError.message}</p>
              </div>
              {lastError.retry && (
                <button
                  onClick={sendRetry}
                  className="px-4 py-2 bg-red-500 text-white rounded-lg text-sm hover:bg-red-600 transition-colors"
                >
                  重试
                </button>
              )}
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.length === 0 && !isProcessing && !isStreaming && !lastError ? (
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
              <>
                {messages.map(msg => (
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
                ))}
                {isStreaming && (
                  <div className="flex justify-start">
                    <div className="max-w-[80%] px-4 py-3 rounded-2xl bg-white text-gray-800 border border-gray-200">
                      <div className="whitespace-pre-wrap">{streamingContent}<span className="animate-pulse">|</span></div>
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="bg-white border-t border-gray-200 p-4">
          <form onSubmit={(e) => sendMessage(e, isProcessing ? 'interrupt' : 'message')} className="max-w-3xl mx-auto flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isProcessing ? "按回车追加信息..." : "输入您的需求..."}
              disabled={!isConnected}
              className="flex-1 px-4 py-3 bg-gray-100 rounded-xl border-2 border-transparent focus:border-meituan-yellow focus:bg-white focus:outline-none transition-all disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || !isConnected}
              className="px-6 py-3 bg-meituan-yellow text-gray-800 rounded-xl hover:opacity-90 transition-opacity font-medium disabled:opacity-50"
            >
              {isProcessing ? '追加' : '发送'}
            </button>
          </form>
          {isProcessing && (
            <p className="max-w-3xl mx-auto text-xs text-gray-400 mt-2 text-center">
              💡 输入后按回车可以追加信息，不打断当前思考
            </p>
          )}
        </footer>
      </div>

      {/* 右侧：方案面板 */}
      {showPlanPanel && currentPlan.length > 0 && (
        <div className="w-[420px] bg-white border-l border-gray-200 flex flex-col">
          <div className="h-20 px-4 border-b border-gray-200 flex items-center justify-between bg-white">
            <div>
              <h2 className="text-lg font-semibold text-gray-800">📋 活动方案</h2>
              <p className="text-xs text-gray-400">{currentPlan.length} 个节点</p>
            </div>
            <div className="flex items-center gap-2">
              {currentPlan.length > 0 && (
                <button
                  onClick={() => setShowMatrixView(true)}
                  className="px-3 py-1.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white text-xs rounded-lg hover:from-indigo-600 hover:to-purple-700 transition-all flex items-center gap-1 shadow-sm"
                  title="矩阵视图选择路径"
                >
                  🔗 矩阵
                </button>
              )}
              <button
                onClick={() => setShowPlanPanel(false)}
                className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors text-lg"
              >
                ✕
              </button>
            </div>
          </div>

          {/* 方案工具条 */}
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500">
              ID: <span className="font-mono text-gray-700">{currentPlanId}</span>
            </span>
            {!hasAlternatives ? (
              <button
                onClick={loadAlternatives}
                disabled={isLoadingAlternatives}
                className="ml-auto px-3 py-1.5 bg-blue-500 text-white text-xs rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50"
              >
                {isLoadingAlternatives ? '加载中...' : '🔄 查看替代方案'}
              </button>
            ) : (
              <span className="ml-auto text-xs text-green-600">✓ 已加载替代方案</span>
            )}
          </div>

          {/* 活动列表 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {currentPlan.map((activity, planIndex) => {
              const isTransport = activity.activity_type === 'transport';
              const nonTransportIdx = getNonTransportActivityIndex(planIndex);
              const alternatives = activityAlternatives[nonTransportIdx];
              const hasAlts = alternatives && alternatives.length > 1;
              const selectedAltIdx = getSelectedAlternativeIndex(nonTransportIdx);
              const isBookable = activity.pre_book?.need && !isTransport;
              const isOrdered = orderedItems[planIndex];

              return (
                <div
                  key={planIndex}
                  className={`rounded-xl p-4 border relative ${
                    isTransport
                      ? 'bg-blue-50 border-blue-200'
                      : 'bg-white border-gray-200'
                  }`}
                >
                  {/* 选中复选框 — 始终显示（可预订且未下单） */}
                  {isBookable && !isOrdered && (
                    <div className="absolute top-3 right-3 z-10">
                      <input
                        type="checkbox"
                        checked={!!selectedItems[planIndex]}
                        onChange={() => toggleSelectItem(planIndex)}
                        className="w-4 h-4 cursor-pointer accent-blue-500"
                      />
                    </div>
                  )}

                  {/* 已下单标记 */}
                  {isOrdered && (
                    <div className="absolute top-3 right-3 z-10 px-2 py-0.5 bg-green-500 text-white text-xs rounded-full">
                      ✓ 已预订
                    </div>
                  )}

                  {/* 替代方案切换箭头 — 右侧 */}
                  {hasAlts && !isTransport && (
                    <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 z-10">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (switchingAltIndex !== null) return;
                          const prevIdx = (selectedAltIdx - 1 + alternatives.length) % alternatives.length;
                          selectAlternative(nonTransportIdx, alternatives[prevIdx].id);
                        }}
                        disabled={switchingAltIndex !== null}
                        className="w-7 h-7 flex items-center justify-center bg-white border border-gray-300 rounded-full text-xs hover:bg-gray-100 transition-all disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
                        title="上一个替代方案"
                      >
                        ▲
                      </button>
                      <span className="text-[10px] text-gray-400 font-mono leading-none">
                        {selectedAltIdx + 1}/{alternatives.length}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (switchingAltIndex !== null) return;
                          const nextIdx = (selectedAltIdx + 1) % alternatives.length;
                          selectAlternative(nonTransportIdx, alternatives[nextIdx].id);
                        }}
                        disabled={switchingAltIndex !== null}
                        className="w-7 h-7 flex items-center justify-center bg-white border border-gray-300 rounded-full text-xs hover:bg-gray-100 transition-all disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
                        title="下一个替代方案"
                      >
                        ▼
                      </button>
                    </div>
                  )}

                  {/* 切换中的加载指示 */}
                  {switchingAltIndex === nonTransportIdx && (
                    <div className="absolute inset-0 bg-white/60 rounded-xl flex items-center justify-center z-20">
                      <div className="animate-spin w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full"></div>
                    </div>
                  )}

                  {/* 交通模式切换箭头 */}
                  {isTransport && activity.from_location && activity.to_location && (
                    <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col items-center gap-1 z-10">
                      <button
                        onClick={(e) => { e.stopPropagation(); cycleTransportMode(planIndex, 'prev'); }}
                        className="w-7 h-7 flex items-center justify-center bg-white border border-blue-300 rounded-full text-xs hover:bg-blue-50 transition-all shadow-sm"
                        title="上一个交通方式"
                      >
                        ▲
                      </button>
                      <span className="text-[10px] text-blue-400 font-mono leading-none">
                        {(() => {
                          const modes = ['walking', 'taxi', 'public_transit', 'driving'];
                          const idx = modes.indexOf(activity.mode || 'taxi');
                          return `${idx >= 0 ? idx + 1 : 2}/4`;
                        })()}
                      </span>
                      <button
                        onClick={(e) => { e.stopPropagation(); cycleTransportMode(planIndex, 'next'); }}
                        className="w-7 h-7 flex items-center justify-center bg-white border border-blue-300 rounded-full text-xs hover:bg-blue-50 transition-all shadow-sm"
                        title="下一个交通方式"
                      >
                        ▼
                      </button>
                    </div>
                  )}

                  <div className="flex items-start gap-3">
                    <span className="text-2xl">
                      {isTransport
                        ? getTransportIcon(activity.mode_icon, activity.mode)
                        : getActivityIcon(activity.activity_type)}
                    </span>
                    <div className={`flex-1 ${(hasAlts && !isTransport) || (isTransport && activity.from_location) ? 'pr-12' : 'pr-8'}`}>
                      <div className="flex items-center gap-2">
                        <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full">
                          {activity.order}
                        </span>
                        <h3 className="font-medium text-gray-800">{activity.name}</h3>
                      </div>
                      <div className="flex items-center gap-2 mt-2 text-sm">
                        <span className="text-gray-500">⏰</span>
                        <span className="text-gray-600">
                          {activity.time_slot?.start} - {activity.time_slot?.end}
                        </span>
                      </div>

                      {/* 交通活动信息 */}
                      {isTransport ? (
                        <div className="mt-2 space-y-1">
                          {activity.from_location?.name && (
                            <p className="text-xs text-gray-500">
                              📍 从: {activity.from_location.name}
                            </p>
                          )}
                          {activity.to_location?.name && (
                            <p className="text-xs text-gray-500">
                              📍 到: {activity.to_location.name}
                            </p>
                          )}
                          <div className="flex items-center gap-4 mt-1 text-xs text-gray-400">
                            {activity.duration_minutes && (
                              <span>⏱️ {activity.duration_minutes}分钟</span>
                            )}
                            {activity.distance_m && (
                              <span>📍 {(activity.distance_m / 1000).toFixed(1)}公里</span>
                            )}
                          </div>
                          {activity.details?.description && (
                            <p className="text-xs text-gray-500 mt-1 italic">
                              {activity.details.description}
                            </p>
                          )}
                        </div>
                      ) : (
                        <>
                          {/* 普通活动信息 */}
                          {activity.location?.address && (
                            <p className="text-sm text-gray-500 mt-1">📍 {activity.location.address}</p>
                          )}
                          {(activity.duration_hours || activity.duration_minutes) && (
                            <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                              {activity.duration_hours && (
                                <span>⏱️ {activity.duration_hours}小时</span>
                              )}
                              {activity.duration_minutes && (
                                <span>⏱️ {activity.duration_minutes}分钟</span>
                              )}
                            </div>
                          )}
                          {activity.details && (
                            <div className="flex items-center gap-4 mt-2 text-xs">
                              {activity.details.rating && (
                                <span className="text-yellow-500">⭐ {activity.details.rating}</span>
                              )}
                              {activity.details.price != null && activity.details.price > 0 && (
                                <span className="text-meituan-yellow">💰 ¥{activity.details.price}</span>
                              )}
                            </div>
                          )}
                          {activity.details?.tags && activity.details.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {activity.details.tags.map((tag, i) => (
                                <span
                                  key={i}
                                  className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                          {isBookable && (
                            <div className="mt-2 p-2 bg-orange-50 rounded-lg">
                              <p className="text-xs text-orange-600">
                                🎫 需要预订: {activity.pre_book?.item}
                              </p>
                            </div>
                          )}
                          {activity.notes && (
                            <p className="text-xs text-gray-500 mt-2 italic">📝 {activity.notes}</p>
                          )}

                          {/* 当前为替代方案的提示标签 */}
                          {hasAlts && selectedAltIdx > 0 && (
                            <div className="mt-2 inline-block px-2 py-0.5 bg-purple-100 text-purple-600 text-[10px] rounded-full">
                              🔄 替代方案 #{selectedAltIdx + 1}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 底部操作区域 — 始终可见 */}
          <div className="p-4 border-t border-gray-200 space-y-3 bg-white">
            {/* 预订信息 + 全选 */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowBookingForm(true)}
                className="px-4 py-2.5 bg-gray-600 text-white text-sm rounded-xl hover:bg-gray-700 transition-colors flex items-center gap-2 shadow-sm"
              >
                📝 填写预订信息
              </button>
              {bookableActivities.length > 0 && (
                <>
                  <button
                    onClick={selectAllUnordered}
                    className="px-3 py-2.5 bg-blue-50 border border-blue-300 text-blue-700 text-sm rounded-xl hover:bg-blue-100 transition-colors font-medium"
                  >
                    全选({unorderedBookable.length})
                  </button>
                  {Object.keys(selectedItems).filter(k => selectedItems[Number(k)]).length > 0 && (
                    <button
                      onClick={() => setSelectedItems({})}
                      className="px-3 py-2.5 bg-white border border-gray-300 text-gray-500 text-xs rounded-xl hover:bg-gray-50 transition-colors"
                    >
                      取消全选
                    </button>
                  )}
                </>
              )}
            </div>

            {/* 当前选中统计 */}
            {bookableActivities.length > 0 && (
              <div className="flex items-center gap-2 text-xs text-gray-500 px-1">
                <span>已选:</span>
                {bookableActivities.map(({ activity, index }) => (
                  <span
                    key={index}
                    className={`px-2 py-0.5 rounded-full cursor-pointer transition-all ${
                      selectedItems[index]
                        ? 'bg-blue-500 text-white'
                        : orderedItems[index]
                          ? 'bg-green-100 text-green-600 line-through'
                          : 'bg-gray-100 text-gray-400 hover:bg-gray-200'
                    }`}
                    onClick={() => {
                      if (!orderedItems[index]) toggleSelectItem(index);
                    }}
                  >
                    {activity.name.slice(0, 6)}
                    {orderedItems[index] ? ' ✓' : selectedItems[index] ? ' ✓' : ''}
                  </span>
                ))}
              </div>
            )}

            {/* 一键下单按钮 */}
            {unorderedBookable.length > 0 ? (
              <button
                onClick={executeSelectedOrders}
                disabled={Object.keys(selectedItems).filter(k => selectedItems[Number(k)]).length === 0}
                className="w-full py-3 bg-meituan-yellow text-gray-800 rounded-xl font-medium hover:opacity-90 transition-all disabled:opacity-50 shadow-sm flex items-center justify-center gap-2"
              >
                🎫 一键下单 ({Object.keys(selectedItems).filter(k => selectedItems[Number(k)]).length}/{unorderedBookable.length}项)
              </button>
            ) : bookableActivities.length > 0 ? (
              <div className="w-full py-3 bg-green-100 text-green-700 rounded-xl font-medium text-center text-sm">
                ✓ 所有可预订项目已完成
              </div>
            ) : (
              <div className="w-full py-3 bg-gray-50 text-gray-400 rounded-xl text-center text-sm">
                当前方案无需预订项目
              </div>
            )}
          </div>
        </div>
      )}

      {/* 矩阵视图全屏覆盖层 — 不离开当前页面，WebSocket 保持连接 */}
      {showMatrixView && currentPlan.length > 0 && (
        <MatrixView
          plan={currentPlan}
          planId={currentPlanId}
          onClose={() => setShowMatrixView(false)}
        />
      )}

      {/* 预订信息表单弹窗 */}
      {showBookingForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-800">📝 预订信息</h3>
              <button
                onClick={() => { setShowBookingForm(false); setBookingFormError(''); setBookingFieldErrors({}); setBookingResult(null); }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  姓名 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={bookingData.user_name}
                  onChange={(e) => {
                    setBookingData(prev => ({ ...prev, user_name: e.target.value }));
                    if (bookingFieldErrors.user_name) setBookingFieldErrors(prev => ({ ...prev, user_name: '' }));
                  }}
                  placeholder="请输入预订人姓名"
                  className={`w-full px-3 py-2 border rounded-lg focus:border-meituan-yellow focus:outline-none ${
                    bookingFieldErrors.user_name ? 'border-red-400 bg-red-50' : 'border-gray-300'
                  }`}
                />
                {bookingFieldErrors.user_name && (
                  <p className="mt-1 text-xs text-red-500">{bookingFieldErrors.user_name}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  手机号 <span className="text-red-500">*</span>
                </label>
                <input
                  type="tel"
                  value={bookingData.phone}
                  onChange={(e) => {
                    setBookingData(prev => ({ ...prev, phone: e.target.value }));
                    if (bookingFieldErrors.phone) setBookingFieldErrors(prev => ({ ...prev, phone: '' }));
                  }}
                  placeholder="请输入手机号"
                  className={`w-full px-3 py-2 border rounded-lg focus:border-meituan-yellow focus:outline-none ${
                    bookingFieldErrors.phone ? 'border-red-400 bg-red-50' : 'border-gray-300'
                  }`}
                />
                {bookingFieldErrors.phone && (
                  <p className="mt-1 text-xs text-red-500">{bookingFieldErrors.phone}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  日期 <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  value={bookingData.date}
                  onChange={(e) => {
                    setBookingData(prev => ({ ...prev, date: e.target.value }));
                    if (bookingFieldErrors.date) setBookingFieldErrors(prev => ({ ...prev, date: '' }));
                  }}
                  className={`w-full px-3 py-2 border rounded-lg focus:border-meituan-yellow focus:outline-none ${
                    bookingFieldErrors.date ? 'border-red-400 bg-red-50' : 'border-gray-300'
                  }`}
                />
                {bookingFieldErrors.date && (
                  <p className="mt-1 text-xs text-red-500">{bookingFieldErrors.date}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  人数 <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  value={bookingData.people}
                  onChange={(e) => {
                    setBookingData(prev => ({ ...prev, people: parseInt(e.target.value) || 2 }));
                    if (bookingFieldErrors.people) setBookingFieldErrors(prev => ({ ...prev, people: '' }));
                  }}
                  min="1"
                  max="20"
                  className={`w-full px-3 py-2 border rounded-lg focus:border-meituan-yellow focus:outline-none ${
                    bookingFieldErrors.people ? 'border-red-400 bg-red-50' : 'border-gray-300'
                  }`}
                />
                {bookingFieldErrors.people && (
                  <p className="mt-1 text-xs text-red-500">{bookingFieldErrors.people}</p>
                )}
              </div>
            </div>

            {bookingFormError && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600">{bookingFormError}</p>
              </div>
            )}

            {bookingResult && (
              <div className={`mt-4 p-4 rounded-lg ${
                bookingResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
              }`}>
                <p className={`text-sm font-medium ${bookingResult.success ? 'text-green-700' : 'text-red-700'}`}>
                  {bookingResult.success ? '✓ ' : '✗ '}{bookingResult.message}
                </p>
                {bookingResult.orders && bookingResult.orders.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {bookingResult.orders.map((order: any, idx: number) => (
                      <p key={idx} className={`text-xs ${order.result.success ? 'text-green-600' : 'text-red-600'}`}>
                      {order.name}: {order.result.success ? '成功' : '失败'}
                      {order.result.order_id && ` (${order.result.order_id})`}
                      {order.result.message && ` - ${order.result.message}`}
                    </p>
                    ))}
                  </div>
                )}
                {bookingResult.details && (
                  <details className="mt-2">
                    <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-800">查看详情</summary>
                    <pre className="mt-2 p-2 bg-white rounded text-xs text-gray-700 max-h-40 overflow-auto">
                      {bookingResult.details}
                    </pre>
                  </details>
                )}
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => { setShowBookingForm(false); setBookingFormError(''); setBookingFieldErrors({}); setBookingResult(null); }}
                disabled={isBookingLoading}
                className="flex-1 py-2.5 border border-gray-300 text-gray-700 rounded-xl hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={validateOrders}
                disabled={isBookingLoading}
                className="flex-1 py-2.5 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50"
              >
                {isBookingLoading ? '处理中...' : '验证订单'}
              </button>
              <button
                onClick={executeSelectedOrders}
                disabled={isBookingLoading}
                className="flex-1 py-2.5 bg-meituan-yellow text-gray-800 rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {isBookingLoading ? '处理中...' : '一键下单'}
              </button>
            </div>

            {isBookingLoading && (
              <div className="mt-3 text-center">
                <div className="inline-block animate-spin w-4 h-4 border-2 border-meituan-yellow border-t-transparent rounded-full mr-2"></div>
                <span className="text-xs text-gray-500">正在处理，请稍候...</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
