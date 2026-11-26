import { useCallback, useEffect, useRef, useState } from 'react'

// Runs an async loader on mount and whenever deps change.
// Returns { data, error, loading, reload, setData }.
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const callId = useRef(0)

  const run = useCallback(() => {
    const id = ++callId.current
    setState((s) => ({ ...s, loading: true, error: null }))
    return loader()
      .then((data) => {
        if (id === callId.current) setState({ data, error: null, loading: false })
        return data
      })
      .catch((error) => {
        if (id === callId.current) setState((s) => ({ ...s, error, loading: false }))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }))
  }, [])

  return { ...state, reload: run, setData }
}
