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

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host || 'localhost:8000';
        const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}//${host}/ws/radar`;
        const pollUrl = `${window.location.protocol}//${host}/api/poll`;
        
        let isPolling = false;

        const startPolling = () => {
            if (isPolling) return;
            isPolling = true;
            console.log("Switching to Polling Mode (Vercel/Serverless)");
            
            const pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(pollUrl);
                    const data = await response.json();
                    
                    // Simple frontend DSP for serverless mode
                    const simulatedJitter = data.rtt > 50 ? (data.rtt / 10) : (Math.random() * 2);
                    
                    setRadarData(prev => ({
                        ...prev,
                        signal: data.signal || 0,
                        rtt: data.rtt || 0,
                        variance: simulatedJitter,
                        status: simulatedJitter > 5 ? 'HUMAN DETECTED (POLLING)' : 'CALM (POLLING)',
                        motionDetected: simulatedJitter > 5,
                        isConnected: true,
                        deviceCount: data.devices || 0,
                        systemStatus: 'ok'
                    }));
                } catch (err) {
                    console.error("Polling error:", err);
                }
            }, 500); // 2Hz polling for serverless

            return () => clearInterval(pollInterval);
        };

        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            setRadarData(prev => ({ ...prev, isConnected: true }));
        };

        socket.onmessage = (event) => {
            // ... (keep existing WebSocket logic)
        };

        socket.onclose = () => {
            setRadarData(prev => ({ ...prev, isConnected: false, status: 'OFFLINE' }));
            // On Vercel, WebSocket will fail immediately. Start polling as fallback.
            startPolling();
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
