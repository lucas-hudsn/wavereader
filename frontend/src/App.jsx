import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import { BreakCardSkeleton } from './components/Skeleton'
import './App.css'

const Landing = lazy(() => import('./pages/Landing'))
const BreakDetail = lazy(() => import('./pages/BreakDetail'))
const Favorites = lazy(() => import('./pages/Favorites'))

function PageFallback() {
  return (
    <div className="breaks-grid">
      {[...Array(6)].map((_, i) => (
        <BreakCardSkeleton key={i} />
      ))}
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route
          index
          element={
            <ErrorBoundary>
              <Suspense fallback={<PageFallback />}>
                <Landing />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path="favorites"
          element={
            <ErrorBoundary>
              <Suspense fallback={<PageFallback />}>
                <Favorites />
              </Suspense>
            </ErrorBoundary>
          }
        />
        <Route
          path=":state/:breakName"
          element={
            <ErrorBoundary>
              <Suspense fallback={<PageFallback />}>
                <BreakDetail />
              </Suspense>
            </ErrorBoundary>
          }
        />
      </Route>
    </Routes>
  )
}

export default App
