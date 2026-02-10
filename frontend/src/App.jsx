import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import BreakDetail from './pages/BreakDetail'
import Favorites from './pages/Favorites'
import './App.css'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="favorites" element={<Favorites />} />
        <Route path=":state/:breakName" element={<BreakDetail />} />
      </Route>
    </Routes>
  )
}

export default App
