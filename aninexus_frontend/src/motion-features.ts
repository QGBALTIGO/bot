import type { FeatureBundle } from 'framer-motion';
import { domMax } from 'framer-motion';

// Lazy-loaded feature bundle for LazyMotion. domMax is required because the
// app uses layout animations (layout prop, AnimatePresence popLayout).
const features: FeatureBundle = {
  ...domMax,
};

export default features;
