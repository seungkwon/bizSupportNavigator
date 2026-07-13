import { useEffect, useMemo, useState } from 'react'
import ForceGraph2D, { type NodeObject } from 'react-force-graph-2d'
import { apiFetch, ApiError } from '../lib/api'

interface GraphNode {
  id: string
  type: string
  label: string
}

interface GraphEdge {
  source: string
  target: string
  type: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

const NODE_COLOR: Record<string, string> = {
  category: '#aa3bff',
  policy: '#2563eb',
  eligibility: '#16a34a',
  exclusion: '#dc2626',
  company_attribute: '#f59e0b',
}

const NODE_TYPE_LABEL: Record<string, string> = {
  category: '카테고리',
  policy: '정책 (클릭 시 상세)',
  eligibility: '자격요건',
  exclusion: '제외요건',
  company_attribute: '기업속성',
}

export default function GraphPage() {
  const [overview, setOverview] = useState<GraphData | null>(null)
  const [detail, setDetail] = useState<GraphData | null>(null)
  const [detailTitle, setDetailTitle] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<GraphData>('/api/policies/graph/overview')
      .then(setOverview)
      .catch((err) => setError(err instanceof ApiError ? err.message : '그래프를 불러오지 못했습니다'))
      .finally(() => setLoading(false))
  }, [])

  const activeData = detail ?? overview

  const graphData = useMemo(() => {
    if (!activeData) return { nodes: [], links: [] }
    return {
      nodes: activeData.nodes.map((n) => ({ ...n })),
      links: activeData.edges.map((e) => ({ ...e })),
    }
  }, [activeData])

  async function handleNodeClick(node: NodeObject) {
    const typedNode = node as unknown as GraphNode
    if (typedNode.type !== 'policy') return
    const policyId = typedNode.id.replace(/^policy:/, '')
    setError(null)
    try {
      const data = await apiFetch<GraphData>(`/api/policies/${policyId}/graph`)
      setDetail(data)
      setDetailTitle(typedNode.label)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '상세 그래프를 불러오지 못했습니다')
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-base-content">정책 그래프 탐색</h1>
        {detail && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setDetail(null)
              setDetailTitle(null)
            }}
          >
            ← 카테고리 개요로
          </button>
        )}
      </div>
      {detailTitle && <p className="mb-3 font-medium text-base-content">{detailTitle}</p>}
      {error && <p className="mb-4 text-sm text-error">{error}</p>}
      {loading ? (
        <p className="text-base-content/70">불러오는 중...</p>
      ) : (
        <div className="overflow-hidden rounded-box border border-base-300">
          <ForceGraph2D
            graphData={graphData}
            nodeId="id"
            nodeLabel="label"
            nodeColor={(node) => NODE_COLOR[(node as unknown as GraphNode).type] ?? '#888'}
            linkLabel="type"
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            onNodeClick={handleNodeClick}
            width={Math.min(window.innerWidth - 48, 1080)}
            height={560}
          />
        </div>
      )}
      <ul className="mt-4 flex flex-wrap gap-4 text-sm">
        {Object.entries(NODE_TYPE_LABEL).map(([type, label]) => (
          <li key={type} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLOR[type] }} />
            {label}
          </li>
        ))}
      </ul>
    </main>
  )
}
