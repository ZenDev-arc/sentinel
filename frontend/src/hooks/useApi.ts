import { useCallback, useEffect, useRef, useState } from 'react'

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: { interval?: number } = {},
) {
  const [data, setData]       = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const timerRef              = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetch = useCallback(async () => {
    try {
      setError(null)
      const result = await fetcher()
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    fetch()
    if (options.interval) {
      timerRef.current = setInterval(fetch, options.interval)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [fetch, options.interval])

  return { data, loading, error, refetch: fetch }
}
