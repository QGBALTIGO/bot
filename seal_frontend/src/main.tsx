import { LazyMotion } from 'framer-motion';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import features from './motion-features';

const container = document.getElementById('root');
if (!container) throw new Error('Root element not found');

createRoot(container).render(
  <LazyMotion features={features} strict>
    <App />
  </LazyMotion>,
);
