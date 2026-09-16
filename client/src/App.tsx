import { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
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
import CookieConsent from './widgets/CookieConsent';
import { reportPageView } from './services/analytics';
import { reportPageVisit } from './services/api/analytics';
import { authService } from './services/auth';
import Data_extraction from './pages/Data_extraction';
import Article_editor from './pages/Article_editor';
import RLE_Databases from './pages/RLE_databases';
import Data_download from './pages/Data_download';
import Social_network from './pages/Social_network';
import SocialProfilePage from './pages/Social_network/ProfilePage';
import Subscription from './pages/Subscription';
import PatternEditor from './pages/Pattern_editor';
import PatternMiner from './pages/Pattern_miner';
import AdminLayout from './pages/Admin';
import DashboardPage from './pages/Admin/pages/Dashboard/ui';
import UsersPage from './pages/Admin/pages/Users/ui';
import UserDetailPage from './pages/Admin/pages/Users/UserDetail';
import TokensPage from './pages/Admin/pages/Tokens/ui';
import SalesPage from './pages/Admin/pages/Sales/ui';
import ExpensesPage from './pages/Admin/pages/Expenses/ui';
import ProfitabilityPage from './pages/Admin/pages/Profitability/ui';
import PlanVsFactPage from './pages/Admin/pages/PlanVsFact/ui';
import PlanEditor from './pages/Admin/pages/PlanVsFact/PlanEditor';
import SettingsPage from './pages/Admin/pages/Settings/ui';
import StrategyPage from './pages/Admin/pages/Strategy/ui';
import UnitEconomicsPage from './pages/Admin/pages/UnitEconomics/ui';
import LaunchPage from './pages/Admin/pages/Launch/ui';

/** Собирает просмотры страниц SPA (маршрут + состояние авторизации). */
function PageViewTracker() {
  const location = useLocation();
  useEffect(() => {
    const authenticated = authService.isAuthenticated();
    const reported = reportPageView(location.pathname, { authenticated });
    if (reported) {
      reportPageVisit(location.pathname);
    }
  }, [location.pathname]);
  return null;
}

function App() {
  return (
    <ViewportProvider>
      <AuthProvider>
        <ToastProvider>
          <Router>
            <CookieConsent />
            <PageViewTracker />
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/km" element={<><Knowledge_map /><Knowledge_map_ui /></>} />
              <Route path="/rle_databases" element={<RLE_Databases/>} />
              <Route path="/introduction" element={<Introduction/>} />
              <Route path="/data_extraction" element={<Data_extraction />} />
              <Route path="/science_articles" element={<><Science_articles /><Knowledge_map_ui /></>} />
              <Route path="/pattern_analysis" element={<><PatternAnalysis /><Knowledge_map_ui /></>} />
              <Route path="/pattern_editor" element={<><PatternEditor /></>} />
              <Route path="/pattern_miner" element={<><PatternMiner /></>} />
              <Route path="/data_download" element={<Data_download />} />
              <Route path="/article_editor" element={<Article_editor />} />
              <Route path="/social_network" element={<Social_network />} />
              <Route path="/social_network/profile/:uid" element={<SocialProfilePage />} />
              <Route path="/subscription" element={<Subscription />} />
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="users" element={<UsersPage />} />
                <Route path="users/:uid" element={<UserDetailPage />} />
                <Route path="tokens" element={<TokensPage />} />
                <Route path="sales" element={<SalesPage />} />
                <Route path="expenses" element={<ExpensesPage />} />
                <Route path="profitability" element={<ProfitabilityPage />} />
                <Route path="plan" element={<PlanVsFactPage />} />
                <Route path="plan/editor" element={<PlanEditor />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="strategy" element={<StrategyPage />} />
                <Route path="unit-economics" element={<UnitEconomicsPage />} />
                <Route path="launch" element={<LaunchPage />} />
              </Route>
            </Routes>
          </Router>
        </ToastProvider>
      </AuthProvider>
    </ViewportProvider>
  )
}

export default App
