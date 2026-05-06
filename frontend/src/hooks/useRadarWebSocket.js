import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook to manage WebSocket connection for WiWave Radar v3.
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
    });

    const socketRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);

    const connect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
        }

        const socket = new WebSocket('ws://localhost:8000/ws/radar');
        socketRef.current = socket;

        socket.onopen = () => {
            setRadarData(prev => ({ ...prev, isConnected: true }));
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setRadarData({
                    signal: data.signal || 0,
                    rtt: data.rtt || 0,
                    variance: data.variance || 0,
                    status: data.status || 'UNKNOWN',
                    motionDetected: data.motion_detected || false,
                    isConnected: true,
                    deviceCount: data.device_count || 0,
                    distance: data.distance || 5.0,
                });
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

    return radarData;
};
