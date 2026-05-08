import React from 'react';
import { useRadarWebSocket } from './hooks/useRadarWebSocket';
import RadarScene from './components/RadarScene';
import { Activity, Wifi, Zap, AlertTriangle, ShieldCheck, HardDrive, Target, Cpu, MapPin, Loader2, Hand } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './App.css';

function App() {
    const { 
        signal, rtt, variance, status, motionDetected, isConnected, 
        deviceCount, distance, learningProgress, isLearning, activeZone, 
        systemStatus, alerts 
    } = useRadarWebSocket();

    return (
        <div className="app-container">
            <div className="radar-container">
                <RadarScene variance={variance} motionDetected={motionDetected} distance={distance} />
                
                <AnimatePresence>
                    {activeZone && activeZone !== 'Unknown' && (
                        <motion.div 
                            className="zone-label-3d"
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0 }}
                        >
                            <MapPin size={16} /> {activeZone}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            <div className="ui-overlay">
                <header>
                    <div className="brand">
                        <Zap className="icon pulse" />
                        <h1>WIWAVE PROFESSIONAL RADAR v4.0</h1>
                    </div>
                    <div className={`connection-status ${isConnected ? (systemStatus === 'ok' ? 'online' : 'error') : 'offline'}`}>
                        {isConnected ? (systemStatus === 'ok' ? 'DUAL-SENSOR ACTIVE' : systemStatus.replace('_', ' ').toUpperCase()) : 'SYSTEM OFFLINE'}
                        <div className="dot"></div>
                    </div>
                </header>

                <main>
                    {/* Alerts Overlay */}
                    <AnimatePresence>
                        {alerts?.fall && (
                            <motion.div className="critical-alert fall" initial={{ opacity: 0, y: -50 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                                <AlertTriangle size={32} />
                                <div>
                                    <h2>EMERGENCY: FALL DETECTED</h2>
                                    <p>Confidence: {(alerts.fall.confidence * 100).toFixed(0)}% | Time: {new Date(alerts.fall.timestamp).toLocaleTimeString()}</p>
                                </div>
                            </motion.div>
                        )}
                        {alerts?.gesture && (
                            <motion.div className="critical-alert gesture" initial={{ opacity: 0, y: -50 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                                <Hand size={32} />
                                <div>
                                    <h2>GESTURE: {alerts.gesture.gesture.toUpperCase()}</h2>
                                    <p>Confidence: {(alerts.gesture.confidence * 100).toFixed(0)}%</p>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

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
                                <div className="label"><Activity size={14} /> JITTER (VAR)</div>
                                <div className="value small">{variance.toFixed(2)}</div>
                            </motion.div>

                            <motion.div className="stat-card mini" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}>
                                <div className="label"><Target size={14} /> EST. RANGE</div>
                                <div className="value small">{distance.toFixed(1)}m</div>
                            </motion.div>
                        </div>
                    </div>

                    <AnimatePresence mode="wait">
                        {systemStatus === 'hw_disconnected' ? (
                            <motion.div key="hw_error" className="status-alert motion" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
                                <AlertTriangle className="status-icon pulse-red" />
                                <div>
                                    <h2>HARDWARE DISCONNECTED</h2>
                                    <p>Wi-Fi adapter missing or disabled. Attempting auto-recovery...</p>
                                </div>
                            </motion.div>
                        ) : isLearning ? (
                            <motion.div key="learning" className="status-alert scanning" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
                                <Loader2 className="status-icon spin" />
                                <div style={{ width: '100%' }}>
                                    <h2>LEARNING ENVIRONMENT...</h2>
                                    <div className="progress-bar-container">
                                        <div className="progress-bar" style={{ width: `${learningProgress * 100}%` }}></div>
                                    </div>
                                    <p>Filling DSP Buffer ({(learningProgress * 100).toFixed(0)}%)</p>
                                </div>
                            </motion.div>
                        ) : (
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
                                            <p>{status}</p>
                                        </div>
                                    </>
                                ) : status.includes('SCANNING') ? (
                                    <>
                                        <Activity className="status-icon pulse-green" />
                                        <div>
                                            <h2>SCANNING...</h2>
                                            <p>{status}</p>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <ShieldCheck className="status-icon" />
                                        <div>
                                            <h2>ENVIRONMENT CALM</h2>
                                            <p>{status}</p>
                                        </div>
                                    </>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </main>

                <footer>
                    <div className="meta">
                        <span>MODE: FUSION (RTT+RSSI)</span>
                        <span className="separator">|</span>
                        <span>ZONE: {activeZone.toUpperCase()}</span>
                        <span className="separator">|</span>
                        <span>ENGINE: PRO-V4</span>
                    </div>
                </footer>
            </div>
        </div>
    );
}

export default App;
