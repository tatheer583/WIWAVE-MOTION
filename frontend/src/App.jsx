import React from 'react';
import { useRadarWebSocket } from './hooks/useRadarWebSocket';
import RadarScene from './components/RadarScene';
import MultiPersonPanel from './components/MultiPersonPanel';
import { Activity, Wifi, Zap, AlertTriangle, ShieldCheck, HardDrive, Target, Cpu, MapPin, Loader2, Hand, Heart } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './App.css';

function App() {
    const { 
        signal, rtt, variance, status, motionDetected, isConnected, 
        deviceCount, distance, learningProgress, isLearning, activeZone, 
        systemStatus, alerts, bpm,
        multiPersonMode, personCount, persons, zoneCongestion
    } = useRadarWebSocket();

    return (
        <div className="app-container">
            <aside className="sidebar">
                <header>
                    <div className="brand">
                        <Zap className="icon pulse" />
                        <h1>WIWAVE v4.0</h1>
                    </div>
                    <div className={`connection-status ${isConnected ? (systemStatus === 'ok' ? 'online' : 'error') : 'offline'}`}>
                        {isConnected ? (systemStatus === 'ok' ? 'ACTIVE' : systemStatus.replace('_', ' ').toUpperCase()) : 'OFFLINE'}
                        <div className="dot"></div>
                    </div>
                </header>

                <main className="sidebar-content">
                    {/* Alerts Section */}
                    <AnimatePresence>
                        {alerts?.fall && (
                            <motion.div className="critical-alert fall" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                                <AlertTriangle size={24} />
                                <div>
                                    <h2>FALL DETECTED</h2>
                                    <p>Confidence: {(alerts.fall.confidence * 100).toFixed(0)}%</p>
                                </div>
                            </motion.div>
                        )}
                        {alerts?.gesture && (
                            <motion.div className="critical-alert gesture" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                                <Hand size={24} />
                                <div>
                                    <h2>GESTURE: {alerts.gesture.gesture.toUpperCase()}</h2>
                                    <p>Confidence: {(alerts.gesture.confidence * 100).toFixed(0)}%</p>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div className="stats-grid">
                        <div className="stat-group">
                            <motion.div className="stat-card" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}>
                                <div className="label"><Wifi size={14} /> MACRO (RSSI)</div>
                                <div className="value">{signal}%</div>
                                <div className="sub-label">Environment Basis</div>
                            </motion.div>

                            <motion.div className="stat-card accent" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
                                <div className="label"><Cpu size={14} /> MICRO (RTT)</div>
                                <div className="value">{rtt} <span className="unit">ms</span></div>
                                <div className="sub-label">Signal Latency</div>
                            </motion.div>
                        </div>

                        <div className="stat-group-mini">
                            <motion.div className="stat-card mini" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}>
                                <div className="label"><Activity size={12} /> JITTER</div>
                                <div className="value small">{variance.toFixed(2)}</div>
                            </motion.div>

                            <motion.div className="stat-card mini" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}>
                                <div className="label"><Target size={12} /> RANGE</div>
                                <div className="value small">{distance.toFixed(1)}m</div>
                            </motion.div>

                            <AnimatePresence>
                                {bpm && (
                                    <motion.div 
                                        className="stat-card mini heart-rate" 
                                        initial={{ opacity: 0, scale: 0.9 }} 
                                        animate={{ opacity: 1, scale: 1 }} 
                                        exit={{ opacity: 0 }}
                                    >
                                        <div className="label"><Heart size={12} className="pulse-red" /> HEART</div>
                                        <div className="value small">{bpm.toFixed(0)} <span className="unit-small">BPM</span></div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </div>

                    <div className="system-status-container">
                        <AnimatePresence mode="wait">
                            {systemStatus === 'hw_disconnected' ? (
                                <motion.div key="hw_error" className="status-indicator error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                                    <AlertTriangle className="icon pulse-red" />
                                    <div>
                                        <h3>HARDWARE DISCONNECTED</h3>
                                        <p>Check Wi-Fi Adapter</p>
                                    </div>
                                </motion.div>
                            ) : isLearning ? (
                                <motion.div key="learning" className="status-indicator scanning" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                                    <Loader2 className="icon spin" />
                                    <div style={{ width: '100%' }}>
                                        <h3>INITIALIZING...</h3>
                                        <div className="progress-bar-container">
                                            <div className="progress-bar" style={{ width: `${learningProgress * 100}%` }}></div>
                                        </div>
                                    </div>
                                </motion.div>
                            ) : (
                                <motion.div 
                                    key={status}
                                    className={`status-indicator ${motionDetected ? 'motion' : status.includes('SCANNING') ? 'scanning' : 'calm'}`}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                >
                                    {motionDetected ? <AlertTriangle className="icon pulse-red" /> : 
                                     status.includes('SCANNING') ? <Activity className="icon pulse-green" /> : 
                                     <ShieldCheck className="icon" />}
                                    <div>
                                        <h3>{motionDetected ? 'MOTION DETECTED' : status.includes('SCANNING') ? 'SCANNING' : 'CALM'}</h3>
                                        <p>{status}</p>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </main>

                <footer>
                    <div className="meta">
                        <div>ENGINE: PRO-V4</div>
                        <div>MODE: {isLearning ? 'CALIBRATING' : 'FUSION'}</div>
                    </div>
                </footer>
            </aside>

            <section className="radar-view">
                <RadarScene 
                    variance={variance} 
                    motionDetected={motionDetected} 
                    distance={distance}
                    multiPersonMode={multiPersonMode}
                    persons={persons}
                />
                
                <AnimatePresence>
                    {activeZone && activeZone !== 'Unknown' && !multiPersonMode && (
                        <motion.div 
                            className="zone-label-3d"
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0 }}
                        >
                            <MapPin size={16} /> {activeZone.toUpperCase()}
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Multi-person panel overlay */}
                {multiPersonMode && (
                    <MultiPersonPanel 
                        personCount={personCount}
                        persons={persons}
                        zoneCongestion={zoneCongestion}
                    />
                )}
            </section>
        </div>
    );
}

export default App;
