import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import './styles/App.css'
import Introduction from './components/Introduction'
import Knowledge_map from './components/Knowledge_map'
import Knowledge_map_ui from './components/Knowledge_map_ui'
import NLP from './components/NLP';
import Science_articles from './components/Science_articles';
import ViewportCoordinates from './components/Knowledge_map/ViewportCoordinates';
import { ViewportProvider } from './contexts/ViewportContext';
import Data_extraction from './components/Data_extraction';
import RLE_Databases from './components/RLE_Databases';

function App() {
  return (
    <ViewportProvider>
      <Router>
        <Routes>
          <Route path="/" element={<>Лендинг</>} />
          <Route path="/km" element={<><Knowledge_map /><Knowledge_map_ui /></>} />
          <Route path="/rle_databases" element={<><RLE_Databases/></>} />
          <Route path="/introduction" element={<><Introduction/></>} />
          <Route path="/data_extraction" element={<Data_extraction />} />
          <Route path="/science_articles" element={<><Science_articles /><Knowledge_map_ui /></>} />
          <Route path="/nlp" element={<><NLP /><Knowledge_map_ui /></>} />
        </Routes>
      </Router>
    </ViewportProvider>
  )
}

export default App
