import { useState, useEffect, useCallback } from 'react'
import { fetchBreakDetail } from '../api'

export default function useBreakDetail(breakName) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const breakData = await fetchBreakDetail(breakName)
      setData(breakData)
      document.title = `${breakData.name} | wavereader`
    } catch (err) {
      setError(err.message)
      document.title = 'wavereader'
    } finally {
      setLoading(false)
    }
  }, [breakName])

  useEffect(() => {
    load()
    return () => { document.title = 'wavereader' }
  }, [load])

  return { data, loading, error, retry: load }
}
