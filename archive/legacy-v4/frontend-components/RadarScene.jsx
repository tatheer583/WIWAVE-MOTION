import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Stars } from '@react-three/drei';
import RadarGrid from './RadarGrid';
import RadarSweep from './RadarSweep';
import HumanSilhouette from './HumanSilhouette';
import MicroMotionBubbles from './MicroMotionBubbles';

/**
 * Main 3D Scene for the WiWave Radar v4 with multi-person support.
 */
const RadarScene = ({ variance, motionDetected, distance, multiPersonMode, persons }) => {
    // Convert zone names to approximate positions
    const getZonePosition = (zone) => {
        const zoneMap = {
            'center': [0, 0, 0],
            'north': [0, 0, -5],
            'south': [0, 0, 5],
            'east': [5, 0, 0],
            'west': [-5, 0, 0],
            'northeast': [3.5, 0, -3.5],
            'northwest': [-3.5, 0, -3.5],
            'southeast': [3.5, 0, 3.5],
            'southwest': [-3.5, 0, 3.5]
        };
        return zoneMap[zone?.toLowerCase()] || [0, 0, 0];
    };

    return (
        <div style={{ width: '100%', height: '100vh', background: '#050510' }}>
            <Canvas shadowAlpha={0}>
                <PerspectiveCamera makeDefault position={[15, 15, 15]} fov={50} />
                <OrbitControls 
                    enablePan={false} 
                    maxPolarAngle={Math.PI / 2.1} 
                    minDistance={5} 
                    maxDistance={40} 
                />
                
                <Stars radius={100} depth={50} count={5000} factor={4} saturation={0} fade speed={1} />
                
                <ambientLight intensity={0.2} />
                <pointLight position={[10, 10, 10]} intensity={1} color="#00ffcc" />
                
                <RadarGrid variance={variance} />
                <RadarSweep />
                
                {/* Multi-person mode: render multiple silhouettes */}
                {multiPersonMode && persons && persons.length > 0 ? (
                    persons.map((person) => {
                        const [x, y, z] = getZonePosition(person.zone);
                        return (
                            <HumanSilhouette 
                                key={person.person_id}
                                visible={true}
                                distance={Math.sqrt(x*x + z*z) || 5}
                                position={[x, y, z]}
                            />
                        );
                    })
                ) : (
                    /* Single-person mode: original behavior */
                    <HumanSilhouette visible={motionDetected} distance={distance} />
                )}
                
                <MicroMotionBubbles jitter={variance} />
                
                <mesh position={[0, -0.9, 0]}>
                    <cylinderGeometry args={[0.2, 0.2, 0.1, 32]} />
                    <meshBasicMaterial color="#00ffcc" />
                </mesh>
            </Canvas>
        </div>
    );
};

export default RadarScene;
