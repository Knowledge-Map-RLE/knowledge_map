import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './styles/App.css'
import Landing from './pages/Landing'
import Introduction from './pages/Introduction'
import Knowledge_map from './pages/Knowledge_map'
import Knowledge_map_ui from './widgets/KnowledgeMapUI'
import PatternAnalysis from './pages/Pattern_analysis';
import Science_articles from './pages/Science_articles';
import { ViewportProvider } from './shared/contexts';
import { ToastProvider } from './shared/ui/Toast';
import { AuthProvider } from './entities/auth';
import Data_extraction from './pages/Data_extraction';
import Article_editor from './pages/Article_editor';
import RLE_Databases from './pages/RLE_databases';
import Data_download from './pages/Data_download';
import Social_network from './pages/Social_network';
import SocialProfilePage from './pages/Social_network/ProfilePage';
import Subscription from './pages/Subscription';

function App() {
  return (
    <ViewportProvider>
      <AuthProvider>
        <ToastProvider>
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
              <Route path="/article_editor" element={<Article_editor />} />
              <Route path="/social_network" element={<Social_network />} />
              <Route path="/social_network/profile/:uid" element={<SocialProfilePage />} />
              <Route path="/subscription" element={<Subscription />} />
            </Routes>
          </Router>
        </ToastProvider>
      </AuthProvider>
    </ViewportProvider>
  )
}

export default App
