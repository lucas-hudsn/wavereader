import { Outlet, Link, NavLink } from 'react-router-dom'
import { useFavorites } from '../context/FavoritesContext'

export default function Layout() {
  const { favorites } = useFavorites()

  return (
    <div className="container">
      <header className="header">
        <Link to="/" className="header-link">
          <h1>wavereader</h1>
          <p className="tagline">AI-powered surf forecasting</p>
        </Link>
        <nav className="header-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            browse
          </NavLink>
          <NavLink to="/favorites" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            favorites {favorites.length > 0 && `(${favorites.length})`}
          </NavLink>
        </nav>
      </header>

      <main>
        <Outlet />
      </main>

      <footer className="footer">
        <p>wavereader - surf forecasting for australian breaks</p>
      </footer>
    </div>
  )
}
