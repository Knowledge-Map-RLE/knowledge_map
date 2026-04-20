import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import './styles/App.css'
import Landing from './pages/Landing'
import Introduction from './pages/Introduction'
import Knowledge_map from './pages/Knowledge_map'
import Knowledge_map_ui from './widgets/KnowledgeMapUI'
import PatternAnalysis from './pages/Pattern_analysis';
import Science_articles from './pages/Science_articles';
import { ViewportProvider } from './shared/contexts';
import Data_extraction from './pages/Data_extraction';
import RLE_Databases from './pages/RLE_databases';
import Data_download from './pages/Data_download';

function App() {
  return (
    <ViewportProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/km" element={<><Knowledge_map /><Knowledge_map_ui /></>} />
          <Route path="/rle_databases" element={<RLE_Databases/>} />
          <Route path="/introduction" element={<Introduction/>} />
          <Route path="/data_extraction" element={<Data_extraction />} />
          <Route path="/science_articles" element={<><Science_articles /><Knowledge_map_ui /></>} />
          <Route path="/pattern_analysis" element={<><PatternAnalysis /><Knowledge_map_ui /></>} />
          <Route path="/data_download" element={<Data_download />} />
        </Routes>
      </Router>
    </ViewportProvider>
  )
}

export default App
