import { canonicalizeEntry } from './native/navigation';
import { LazyMotion } from 'framer-motion';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import features from './motion-features';
import { installPtBR } from './ptBR';
import { installTelegramViewport } from './telegram/viewport';

canonicalizeEntry();
installPtBR();
const disposeViewport = installTelegramViewport();
if (import.meta.hot) import.meta.hot.dispose(disposeViewport);

const container = document.getElementById('root');
if (!container) throw new Error('Elemento raiz não encontrado');

createRoot(container).render(
  <LazyMotion features={features} strict>
    <App />
  </LazyMotion>,
);
