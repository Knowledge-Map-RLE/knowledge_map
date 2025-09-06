import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import './styles/App.css'
import Knowledge_map from './components/Knowledge_map'
import Knowledge_map_ui from './components/Knowledge_map_ui'
import NLP from './components/NLP';
import Science_articles from './components/Science_articles';
import ViewportCoordinates from './components/Knowledge_map/ViewportCoordinates';
import { ViewportProvider } from './contexts/ViewportContext';

function App() {
  return (
    <ViewportProvider>
      <Router>
        <Routes>
          <Route path="/" element={<><Knowledge_map /><Knowledge_map_ui /></>} />
          <Route path="/nlp" element={<><NLP /><Knowledge_map_ui /></>} />
          <Route path="/science_articles" element={<><Science_articles /><Knowledge_map_ui /></>} />
        </Routes>
        
        {/* Глобальный компонент координат - поверх всех страниц */}
        <ViewportCoordinates />
      </Router>
    </ViewportProvider>
  )
}

export default App
