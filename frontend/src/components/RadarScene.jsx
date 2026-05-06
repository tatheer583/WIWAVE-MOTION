import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Stars } from '@react-three/drei';
import RadarGrid from './RadarGrid';
import RadarSweep from './RadarSweep';
import HumanSilhouette from './HumanSilhouette';
import MicroMotionBubbles from './MicroMotionBubbles';

/**
 * Main 3D Scene for the WiWave Radar v3.
 */
const RadarScene = ({ variance, motionDetected, distance }) => {
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
                <HumanSilhouette visible={motionDetected} distance={distance} />
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
