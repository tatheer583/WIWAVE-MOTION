import React from 'react';
import { useRadarWebSocket } from './hooks/useRadarWebSocket';
import RadarScene from './components/RadarScene';
import { Activity, Wifi, Zap, AlertTriangle, ShieldCheck, HardDrive, Target, Cpu } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './App.css';

function App() {
    const { signal, rtt, variance, status, motionDetected, isConnected, deviceCount, distance } = useRadarWebSocket();

    return (
        <div className="app-container">
            <div className="radar-container">
                <RadarScene variance={variance} motionDetected={motionDetected} distance={distance} />
            </div>

            <div className="ui-overlay">
                <header>
                    <div className="brand">
                        <Zap className="icon pulse" />
                        <h1>WIWAVE PROFESSIONAL RADAR v3.0</h1>
                    </div>
                    <div className={`connection-status ${isConnected ? 'online' : 'offline'}`}>
                        {isConnected ? 'DUAL-SENSOR ACTIVE' : 'SYSTEM OFFLINE'}
                        <div className="dot"></div>
                    </div>
                </header>

                <main>
                    <div className="stats-grid">
                        <div className="sub-grid">
                            <motion.div className="stat-card" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}>
                                <div className="label"><Wifi size={16} /> MACRO (RSSI)</div>
                                <div className="value">{signal}%</div>
                                <div className="sub-label">Slow-Refresh Basis</div>
                            </motion.div>

                            <motion.div className="stat-card accent" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
                                <div className="label"><Cpu size={16} /> MICRO (RTT)</div>
                                <div className="value">{rtt} <span className="unit">ms</span></div>
                                <div className="sub-label">Real-time Latency</div>
                            </motion.div>
                        </div>

                        <div className="sub-grid">
                            <motion.div className="stat-card mini" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}>
                                <div className="label"><Activity size={14} /> JITTER (VARIANCE)</div>
                                <div className="value small">{variance.toFixed(2)}</div>
                            </motion.div>

                            <motion.div className="stat-card mini" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}>
                                <div className="label"><Target size={14} /> EST. RANGE</div>
                                <div className="value small">{distance.toFixed(1)}m</div>
                            </motion.div>
                        </div>

                        <motion.div className="stat-card" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 }}>
                            <div className="label"><HardDrive size={16} /> NETWORK LOAD</div>
                            <div className="value">{deviceCount} <span className="unit">Devices</span></div>
                        </motion.div>
                    </div>

                    <AnimatePresence mode="wait">
                        <motion.div 
                            key={status}
                            className={`status-alert ${motionDetected ? 'motion' : status.includes('SCANNING') ? 'scanning' : 'calm'}`}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -20 }}
                        >
                            {motionDetected ? (
                                <>
                                    <AlertTriangle className="status-icon pulse-red" />
                                    <div>
                                        <h2>HUMAN SIGNATURE DETECTED</h2>
                                        <p>{status.includes('ACTIVE') ? 'Dynamic movement confirmed via RTT Jitter.' : 'Sustained micro-fluctuations identified.'}</p>
                                    </div>
                                </>
                            ) : status.includes('SCANNING') ? (
                                <>
                                    <Activity className="status-icon pulse-green" />
                                    <div>
                                        <h2>SCANNING...</h2>
                                        <p>Dual-sensor fusion active. Monitoring RF environment.</p>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <ShieldCheck className="status-icon" />
                                    <div>
                                        <h2>ENVIRONMENT CALM</h2>
                                        <p>No human interference detected in current session.</p>
                                    </div>
                                </>
                            )}
                        </motion.div>
                    </AnimatePresence>
                </main>

                <footer>
                    <div className="meta">
                        <span>MODE: DUAL-SENSOR FUSION (RTT + RSSI)</span>
                        <span className="separator">|</span>
                        <span>POLL RATE: 100ms</span>
                        <span className="separator">|</span>
                        <span>ENGINE: PRO-V3</span>
                    </div>
                </footer>
            </div>
        </div>
    );
}

export default App;
