import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook to manage WebSocket connection for WiWave Radar v4.
 */
export const useRadarWebSocket = () => {
    const [radarData, setRadarData] = useState({
        signal: 0,
        rtt: 0,
        variance: 0,
        status: 'OFFLINE',
        motionDetected: false,
        isConnected: false,
        deviceCount: 0,
        distance: 5.0,
        learningProgress: 0,
        isLearning: false,
        activeZone: 'Unknown',
        systemStatus: 'ok', // 'hw_disconnected', 'no_signal', 'ok'
    });

    const [alerts, setAlerts] = useState({
        fall: null,
        gesture: null
    });

    const socketRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);

    const connect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
        }

        const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/radar';
        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            setRadarData(prev => ({ ...prev, isConnected: true }));
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'system_status') {
                    setRadarData(prev => ({ ...prev, systemStatus: data.status, status: data.status === 'hw_disconnected' ? 'HARDWARE ERROR' : 'NO SIGNAL' }));
                } else if (data.type === 'fall_alert') {
                    setAlerts(prev => ({ ...prev, fall: data }));
                    // Auto-clear alert after 5s
                    setTimeout(() => setAlerts(prev => ({ ...prev, fall: null })), 5000);
                } else if (data.type === 'gesture') {
                    setAlerts(prev => ({ ...prev, gesture: data }));
                    // Auto-clear gesture after 3s
                    setTimeout(() => setAlerts(prev => ({ ...prev, gesture: null })), 3000);
                } else if (data.type === 'radar_update' || !data.type) {
                    setRadarData(prev => ({
                        ...prev,
                        signal: data.signal || 0,
                        rtt: data.rtt || 0,
                        variance: data.variance || 0,
                        status: data.status || 'UNKNOWN',
                        motionDetected: data.motion_detected || false,
                        isConnected: true,
                        deviceCount: data.device_count || 0,
                        distance: data.distance || 5.0,
                        learningProgress: data.learning_progress || 0,
                        isLearning: data.is_learning || false,
                        activeZone: data.active_zone || 'Unknown',
                        systemStatus: 'ok'
                    }));
                }
            } catch (err) {
                console.error("Error parsing radar data:", err);
            }
        };

        socket.onclose = () => {
            setRadarData(prev => ({ ...prev, isConnected: false, status: 'OFFLINE' }));
            reconnectTimeoutRef.current = setTimeout(connect, 3000);
        };

        socket.onerror = () => {
            socket.close();
        };
    }, []);

    useEffect(() => {
        connect();
        return () => {
            if (socketRef.current) socketRef.current.close();
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        };
    }, [connect]);

    return { ...radarData, alerts };
};
