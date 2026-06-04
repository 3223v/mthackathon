'use client';

import { useState, useEffect, useCallback } from 'react';

// ==================== 类型 ====================

interface PlanActivity {
  order: number;
  time_slot: { start: string; end: string };
  activity_type: string;
  name: string;
  item_id?: string;
  location?: { lat: number; lng: number; address?: string; name?: string };
  duration_hours?: number;
  duration_minutes?: number;
  distance_m?: number;
  mode?: string;
  mode_label?: string;
  mode_icon?: string;
  from_location?: { lat: number; lng: number; address?: string; name?: string };
  to_location?: { lat: number; lng: number; address?: string; name?: string };
  details?: { rating?: number; price?: number; tags?: string[]; description?: string };
  pre_book?: { need: boolean; type: string; item: string };
  notes?: string;
}

interface MatrixNode {
  id: string;
  label: string;
  is_original: boolean;
  activity: PlanActivity;
  transport_info?: { mode: string; mode_label: string; mode_icon: string; duration_minutes: number; distance_m: number };
  llm_score?: number;
}

interface MatrixData {
  plan_id: string;
  matrix: MatrixNode[][];
  column_labels: string[];
  column_types: string[];
}

// ==================== 常量 ====================

const TRANSPORT_BG: Record<string, string> = {
  walking: 'from-green-50 to-emerald-50 border-green-300',
  public_transit: 'from-blue-50 to-sky-50 border-blue-300',
  taxi: 'from-amber-50 to-yellow-50 border-amber-300',
  driving: 'from-red-50 to-rose-50 border-red-300',
};

const TRANSPORT_BG_SELECTED: Record<string, string> = {
  walking: 'from-green-100 to-emerald-100 border-green-500 ring-green-400',
  public_transit: 'from-blue-100 to-sky-100 border-blue-500 ring-blue-400',
  taxi: 'from-amber-100 to-yellow-100 border-amber-500 ring-amber-400',
  driving: 'from-red-100 to-rose-100 border-red-500 ring-red-400',
};

const TRANSPORT_ICONS: Record<string, string> = {
  walking: '🚶', public_transit: '🚌', taxi: '🚕', driving: '🚗',
};

const ACTIVITY_BG = 'from-white to-gray-50 border-gray-200';
const ACTIVITY_BG_SELECTED = 'from-blue-50 to-indigo-50 border-blue-500 ring-blue-400';
const ACTIVITY_ICONS: Record<string, string> = {
  attraction: '🏛️', restaurant: '🍽️', activity: '🎯', cafe: '☕', free_time: '🕐',
};

interface Props {
  plan: PlanActivity[];
  planId: string;
  onClose: () => void;
}

export default function MatrixView({ plan, planId, onClose }: Props) {
  const [matrixData, setMatrixData] = useState<MatrixData | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCol, setHoveredCol] = useState<number | null>(null);

  // 加载矩阵
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await fetch('http://localhost:8000/api/plan/matrix', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan_id: planId, plan, top_k: 3 }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data: MatrixData = await resp.json();
        if (cancelled) return;
        setMatrixData(data);
        setSelectedIds(data.matrix.map(col => col[0]?.id || ''));
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载失败');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [plan, planId]);

  const selectNode = useCallback((colIdx: number, nodeId: string) => {
    setSelectedIds(prev => { const n = [...prev]; n[colIdx] = nodeId; return n; });
  }, []);

  const submitPath = async () => {
    if (!matrixData) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const resp = await fetch('http://localhost:8000/api/plan/reroute-matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId, selected_ids: selectedIds, matrix: matrixData.matrix }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      if (result.plan) {
        // 通过自定义事件传回结果
        window.dispatchEvent(new CustomEvent('matrix_result', { detail: { plan: result.plan, planId: result.plan_id || planId } }));
      }
    } catch (e: any) {
      setError(e?.message || '提交失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 键盘导航
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const visiblePlanId = planId || '...';
  const transportCols = matrixData?.column_types?.filter(t => t === 'transport').length ?? 0;
  const activityCols = matrixData?.column_types?.filter(t => t === 'activity').length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-100 animate-in fade-in duration-200">
      {/* ====== 顶部导航栏 ====== */}
      <header className="h-16 bg-gradient-to-r from-indigo-600 to-purple-600 text-white flex items-center justify-between px-6 shadow-lg shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/15 hover:bg-white/25 transition-colors text-lg"
            title="关闭 (Esc)"
          >
            ✕
          </button>
          <div className="h-6 w-px bg-white/25" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">路径选择矩阵</h1>
            <p className="text-xs text-white/70">plan: {visiblePlanId}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* 统计 */}
          <div className="flex items-center gap-3 text-xs text-white/80">
            <span className="px-2.5 py-1 bg-white/15 rounded-full">📍 {activityCols} 活动</span>
            <span className="px-2.5 py-1 bg-white/15 rounded-full">🚕 {transportCols} 交通</span>
            <span className="px-2.5 py-1 bg-white/15 rounded-full">📐 {matrixData?.matrix.length ?? 0} 列</span>
          </div>
          <div className="h-6 w-px bg-white/25" />

          {/* 操作按钮 */}
          <button
            onClick={() => matrixData && setSelectedIds(matrixData.matrix.map(c => c[0]?.id || ''))}
            className="px-4 py-2 bg-white/15 hover:bg-white/25 rounded-xl text-sm transition-colors"
          >
            🔄 重置
          </button>
          <button
            onClick={submitPath}
            disabled={isSubmitting || !matrixData}
            className="px-5 py-2 bg-white text-indigo-700 rounded-xl font-bold text-sm hover:bg-gray-100 transition-all disabled:opacity-50 shadow-md flex items-center gap-2"
          >
            {isSubmitting ? (
              <><div className="animate-spin w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full" /> 生成中</>
            ) : (
              '✅ 确认路径'
            )}
          </button>
        </div>
      </header>

      {/* ====== 主体内容 ====== */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin w-14 h-14 border-4 border-indigo-300 border-t-indigo-600 rounded-full mx-auto mb-5" />
            <p className="text-gray-600 text-lg font-medium">正在构建方案矩阵...</p>
            <p className="text-gray-400 text-sm mt-2">查询替代方案，为每个节点生成候选</p>
          </div>
        </div>
      ) : error && !matrixData ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-white rounded-2xl p-10 shadow-lg text-center max-w-md">
            <span className="text-5xl mb-5 block">⚠️</span>
            <h2 className="text-xl font-bold text-gray-800 mb-3">加载失败</h2>
            <p className="text-gray-500 mb-6">{error}</p>
            <button onClick={onClose} className="px-6 py-2.5 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 transition-colors font-medium">
              返回对话
            </button>
          </div>
        </div>
      ) : matrixData ? (
        <>
          {/* 提示条 */}
          <div className="bg-white border-b border-gray-200 px-6 py-3 shrink-0">
            <div className="flex items-center gap-3 max-w-6xl mx-auto">
              <span className="text-xl">💡</span>
              <div className="text-sm text-gray-600">
                每列选择一个节点，形成完整路径。点击顶部 <strong className="text-indigo-600">✅ 确认路径</strong> 生成方案。
                选中节点用 <span className="inline-block w-3 h-3 bg-blue-500 rounded-full align-middle mx-0.5" /> 标识。
              </div>
            </div>
          </div>

          {/* 矩阵网格 */}
          <div className="flex-1 overflow-auto p-8">
            <div className="flex gap-5 justify-center min-w-max mx-auto pb-8">
              {matrixData.matrix.map((column, colIdx) => {
                const isTransport = matrixData.column_types[colIdx] === 'transport';
                const label = matrixData.column_labels[colIdx] || `位置${colIdx + 1}`;

                return (
                  <div key={colIdx} className="flex flex-col items-center group" style={{ minWidth: 220 }}>
                    {/* 列标题 */}
                    <div className={`
                      mb-3 px-4 py-2 rounded-xl text-xs font-bold whitespace-nowrap shadow-sm transition-all
                      ${isTransport
                        ? 'bg-gradient-to-r from-blue-500 to-sky-500 text-white'
                        : 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'}
                      ${hoveredCol === colIdx ? 'scale-105' : ''}
                    `}>
                      {isTransport ? '🚕' : '📍'} {label}
                    </div>

                    {/* 节点列表 */}
                    <div className="flex flex-col gap-3 w-full">
                      {column.map((node, rowIdx) => {
                        const isSelected = selectedIds[colIdx] === node.id;
                        const isTransportNode = !!node.transport_info;
                        const mode = node.transport_info?.mode || '';
                        const actType = node.activity?.activity_type || '';

                        return (
                          <button
                            key={node.id}
                            onClick={() => selectNode(colIdx, node.id)}
                            onMouseEnter={() => setHoveredCol(colIdx)}
                            onMouseLeave={() => setHoveredCol(null)}
                            className={`
                              w-full px-4 py-3.5 rounded-xl text-left transition-all duration-200 cursor-pointer
                              border-2 bg-gradient-to-r
                              ${isSelected
                                ? (isTransportNode
                                    ? `${TRANSPORT_BG_SELECTED[mode] || 'from-blue-100 to-sky-100 border-blue-500'} ring-2 shadow-lg scale-[1.03]`
                                    : `${ACTIVITY_BG_SELECTED} ring-2 shadow-lg scale-[1.03]`)
                                : (isTransportNode
                                    ? `${TRANSPORT_BG[mode] || 'from-gray-50 to-gray-50 border-gray-200'} hover:shadow-md hover:scale-[1.01]`
                                    : `${ACTIVITY_BG} hover:shadow-md hover:scale-[1.01]`)
                              }
                            `}
                          >
                            {/* 头部：选中指示器 + 类型图标 + 标签 */}
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all shrink-0 ${
                                isSelected ? 'border-blue-500 bg-blue-500' : 'border-gray-300 bg-white'
                              }`}>
                                {isSelected && <span className="text-white text-[10px] leading-none">✓</span>}
                              </span>
                              <span className="text-lg shrink-0">
                                {isTransportNode
                                  ? TRANSPORT_ICONS[mode] || '🚕'
                                  : ACTIVITY_ICONS[actType] || '📍'}
                              </span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ml-auto shrink-0 ${
                                node.is_original
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-gray-100 text-gray-500'
                              }`}>
                                {node.is_original ? '原始' : `替${rowIdx}`}
                              </span>
                            </div>

                            {/* 名称 */}
                            <div className={`text-sm font-semibold truncate ${
                              isSelected ? 'text-gray-900' : 'text-gray-700'
                            }`}>
                              {node.label}
                            </div>

                            {/* 详情 */}
                            {isTransportNode && node.transport_info && (
                              <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                                <span className="flex items-center gap-1"><span className="text-gray-400">⏱</span> {node.transport_info.duration_minutes}分</span>
                                <span className="flex items-center gap-1"><span className="text-gray-400">📍</span> {(node.transport_info.distance_m / 1000).toFixed(1)}km</span>
                              </div>
                            )}
                            {!isTransportNode && node.activity?.details && (
                              <div className="flex items-center gap-3 mt-1.5 text-xs">
                                {node.activity.details.rating && (
                                  <span className="text-amber-500 font-medium">⭐ {node.activity.details.rating}</span>
                                )}
                                {node.activity.details.price != null && node.activity.details.price > 0 && (
                                  <span className="text-orange-500 font-bold">¥{node.activity.details.price}</span>
                                )}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>

                    {/* 列间箭头 */}
                    {colIdx < matrixData.matrix.length - 1 && (
                      <div className="mt-3 text-2xl text-gray-300 select-none">↓</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ====== 底部状态栏 ====== */}
          <div className="bg-white border-t border-gray-200 px-6 py-4 shrink-0 shadow-lg">
            <div className="max-w-6xl mx-auto flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-gray-700">当前路径:</span>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {selectedIds.map((id, i) => {
                    const col = matrixData.matrix[i];
                    const node = col?.find(n => n.id === id);
                    const isT = node?.transport_info != null;
                    return (
                      <div key={i} className="flex items-center gap-1.5">
                        {i > 0 && <span className="text-gray-300 text-xs">→</span>}
                        <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                          isT
                            ? 'bg-blue-100 text-blue-700 border border-blue-200'
                            : 'bg-purple-100 text-purple-700 border border-purple-200'
                        }`}>
                          {node?.label || id}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">
                  已选 {selectedIds.length}/{matrixData.matrix.length} 列
                </span>
                <button
                  onClick={() => setSelectedIds(matrixData.matrix.map(c => c[0]?.id || ''))}
                  className="px-4 py-2 border border-gray-300 text-gray-600 rounded-xl text-sm hover:bg-gray-50 transition-colors"
                >
                  🔄 重置为原始方案
                </button>
                <button
                  onClick={submitPath}
                  disabled={isSubmitting || selectedIds.length === 0}
                  className="px-6 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl font-bold text-sm hover:from-indigo-600 hover:to-purple-700 transition-all disabled:opacity-50 shadow-lg flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <><div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> 生成中</>
                  ) : (
                    <>✅ 确认路径 ({selectedIds.length}/{matrixData.matrix.length})</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
