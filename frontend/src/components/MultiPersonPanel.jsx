import { motion, AnimatePresence } from 'framer-motion';
import { Users, User, Activity, MapPin } from 'lucide-react';

/**
 * Per-person color palette — each person gets a distinct neon color.
 */
const PERSON_COLORS = [
    '#00ffcc', // teal  (person 1)
    '#ff6b6b', // coral (person 2)
    '#ffd93d', // amber (person 3)
    '#6bcbff', // sky   (person 4)
    '#c77dff', // violet(person 5)
];

const activityIcon = (activity) => {
    switch (activity) {
        case 'walking':  return '🚶';
        case 'breathing': return '🫁';
        case 'still':    return '🧍';
        case 'gesture':  return '👋';
        default:         return '❓';
    }
};

const zoneLabel = (zone) => {
    if (!zone) return '—';
    return zone.charAt(0).toUpperCase() + zone.slice(1);
};

/**
 * MultiPersonPanel — sidebar section showing per-person cards.
 * Renders only when personCount > 1.
 */
const MultiPersonPanel = ({ persons = [], personCount = 0, zoneCongestion = {} }) => {
    if (personCount <= 1) return null;

    return (
        <motion.div
            className="multi-person-panel"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
        >
            {/* Header */}
            <div className="mp-header">
                <Users size={14} />
                <span>MULTI-PERSON DETECTION</span>
                <span className="mp-count">{personCount}</span>
            </div>

            {/* Zone congestion badges */}
            {Object.entries(zoneCongestion).some(([, v]) => v) && (
                <div className="mp-congestion">
                    {Object.entries(zoneCongestion).map(([zone, congested]) =>
                        congested ? (
                            <span key={zone} className="congestion-badge">
                                ⚠ {zoneLabel(zone)} congested
                            </span>
                        ) : null
                    )}
                </div>
            )}

            {/* Per-person cards */}
            <div className="mp-persons">
                <AnimatePresence>
                    {persons.map((person, idx) => {
                        const color = PERSON_COLORS[idx % PERSON_COLORS.length];
                        return (
                            <motion.div
                                key={person.person_id}
                                className="mp-person-card"
                                style={{ borderColor: color }}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 10 }}
                                transition={{ delay: idx * 0.05 }}
                            >
                                {/* Person ID badge */}
                                <div className="mp-person-id" style={{ color }}>
                                    <User size={11} />
                                    P{person.person_id}
                                </div>

                                {/* Activity */}
                                <div className="mp-person-activity">
                                    <span className="mp-activity-icon">
                                        {activityIcon(person.activity)}
                                    </span>
                                    <span className="mp-activity-label">
                                        {person.activity || 'unknown'}
                                    </span>
                                </div>

                                {/* Zone + confidence row */}
                                <div className="mp-person-meta">
                                    <span className="mp-zone">
                                        <MapPin size={10} />
                                        {zoneLabel(person.position_zone)}
                                    </span>
                                    <span className="mp-confidence">
                                        <Activity size={10} />
                                        {typeof person.confidence === 'number'
                                            ? `${person.confidence.toFixed(0)}%`
                                            : '—'}
                                    </span>
                                </div>

                                {/* Confidence bar */}
                                <div className="mp-confidence-bar-bg">
                                    <div
                                        className="mp-confidence-bar-fill"
                                        style={{
                                            width: `${person.confidence || 0}%`,
                                            background: color,
                                        }}
                                    />
                                </div>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>
            </div>
        </motion.div>
    );
};

export default MultiPersonPanel;
