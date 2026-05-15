import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook to manage WebSocket connection for WiWave Radar v4.
 * Supports both single-person and multi-person detection payloads.
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
        bpm: null,
        systemStatus: 'ok',
        // Multi-person fields
        personCount: 0,
        persons: [],
        zoneCongestion: {},
        multiPersonMode: 'single_person',
    });

    const [alerts, setAlerts] = useState({
        fall: null,
        gesture: null,
    });

    const socketRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);

    const connect = useCallback(() => {
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host || 'localhost:8000';
        const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}//${host}/ws/radar`;
        const pollUrl = `${window.location.protocol}//${host}/api/poll`;

        let isPolling = false;

        const startPolling = () => {
            if (isPolling) return;
            isPolling = true;
            console.log('Switching to Polling Mode (Vercel/Serverless)');

            const pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(pollUrl);
                    const data = await response.json();

                    if (data.type === 'radar_update' || data.status) {
                        setRadarData(prev => ({
                            ...prev,
                            signal: data.signal || 0,
                            rtt: data.rtt || 0,
                            variance: data.variance || 0,
                            status: data.status || 'CONNECTED',
                            motionDetected: data.motion_detected || false,
                            distance: data.distance || prev.distance,
                            learningProgress: data.learning_progress || 1.0,
                            isLearning: (data.learning_progress || 1.0) < 1.0,
                            activeZone: data.active_zone || prev.activeZone,
                            bpm: data.bpm || null,
                            isConnected: true,
                            systemStatus: 'ok',
                            personCount: data.person_count || 0,
                            persons: data.persons || [],
                            zoneCongestion: data.zone_congestion || {},
                            multiPersonMode: data.multi_person_mode || 'single_person',
                        }));
                    } else {
                        setRadarData(prev => ({
                            ...prev,
                            signal: data.signal || 0,
                            rtt: data.rtt || 0,
                            isConnected: true,
                            status: 'POLLING (RAW)',
                            systemStatus: 'ok',
                        }));
                    }
                } catch (err) {
                    console.error('Polling error:', err);
                }
            }, 1000);

            return () => clearInterval(pollInterval);
        };

        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            setRadarData(prev => ({ ...prev, isConnected: true }));
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'radar_update') {
                    setRadarData(prev => ({
                        ...prev,
                        signal: data.signal,
                        rtt: data.rtt,
                        variance: data.variance,
                        status: data.status,
                        motionDetected: data.motion_detected,
                        distance: data.distance,
                        learningProgress: data.learning_progress,
                        isLearning: data.learning_progress < 1.0,
                        activeZone: data.active_zone,
                        bpm: data.bpm,
                        systemStatus: 'ok',
                        // Multi-person fields from radar_update
                        personCount: data.person_count || 0,
                        persons: data.persons || [],
                        zoneCongestion: data.zone_congestion || {},
                        multiPersonMode: data.multi_person_mode || 'single_person',
                    }));
                } else if (data.type === 'multi_person_update') {
                    // Dedicated multi-person update message
                    setRadarData(prev => ({
                        ...prev,
                        personCount: data.person_count || 0,
                        persons: data.persons || [],
                        zoneCongestion: data.zone_congestion || {},
                        multiPersonMode: data.mode || 'multi_person',
                    }));
                } else if (data.type === 'fall_alert') {
                    setAlerts(prev => ({ ...prev, fall: data }));
                    setTimeout(() => setAlerts(prev => ({ ...prev, fall: null })), 5000);
                } else if (data.type === 'gesture') {
                    setAlerts(prev => ({ ...prev, gesture: data }));
                    setTimeout(() => setAlerts(prev => ({ ...prev, gesture: null })), 3000);
                } else if (data.type === 'system_status') {
                    setRadarData(prev => ({ ...prev, systemStatus: data.status }));
                }
            } catch (err) {
                console.error('Error parsing WebSocket message:', err);
            }
        };

        socket.onclose = () => {
            setRadarData(prev => ({ ...prev, isConnected: false, status: 'OFFLINE' }));
            if (window.location.hostname.includes('vercel.app')) {
                startPolling();
            } else {
                reconnectTimeoutRef.current = setTimeout(connect, 3000);
            }
        };

        socket.onerror = () => { socket.close(); };
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
