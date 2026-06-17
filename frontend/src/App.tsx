import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Home from './pages/Home'
import Docs from './pages/Docs'
import Commands from './pages/Commands'
import Agents from './pages/Agents'
import Dashboard from './pages/Dashboard'

function PageLayout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation()
  const isHome = pathname === '/'
  return (
    <div className="flex flex-col min-h-screen">
      <Navbar />
      <main className={`flex-1 ${isHome ? '' : 'pt-16'}`}>
        {children}
      </main>
      <Footer />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter basename="/sentinel">
      <PageLayout>
        <Routes>
          <Route path="/"          element={<Home />} />
          <Route path="/docs"      element={<Docs />} />
          <Route path="/commands"  element={<Commands />} />
          <Route path="/agents"    element={<Agents />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </PageLayout>
    </BrowserRouter>
  )
}
