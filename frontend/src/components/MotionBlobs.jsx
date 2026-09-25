import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * Renders glowing blobs/particles when motion is detected.
 */
const MotionBlobs = ({ motionDetected }) => {
    const groupRef = useRef();
    
    // Deterministic illustration positions; these are not measured targets.
    const blobData = useMemo(() => {
        return Array.from({ length: 15 }, (_, i) => ({
            position: [
                Math.sin(i * 2.4) * 7.5,
                (i % 10) / 2,
                Math.cos(i * 1.7) * 7.5
            ],
            speed: 0.5 + (i % 5) * 0.2,
            offset: i * 2.4,
            scale: 0.2 + (i % 4) * 0.2
        }));
    }, []);

    useFrame((state) => {
        if (!groupRef.current) return;
        
        const time = state.clock.getElapsedTime();
        
        // Target opacity based on motion
        const targetOpacity = motionDetected ? 0.6 : 0;
        
        groupRef.current.children.forEach((child, i) => {
            const data = blobData[i];
            
            // Pulse scale
            const pulse = 1 + Math.sin(time * data.speed + data.offset) * 0.2;
            child.scale.setScalar(data.scale * pulse * (motionDetected ? 1 : 0.1));
            
            // Floating movement
            child.position.y = data.position[1] + Math.sin(time * 0.5 + data.offset) * 0.5;
            
            // Fade opacity
            child.material.opacity = THREE.MathUtils.lerp(child.material.opacity, targetOpacity, 0.1);
        });
    });

    return (
        <group ref={groupRef}>
            {blobData.map((data, i) => (
                <mesh key={i} position={data.position}>
                    <sphereGeometry args={[1, 16, 16]} />
                    <meshBasicMaterial 
                        color="#ff3366" 
                        transparent 
                        opacity={0} 
                        blending={THREE.AdditiveBlending}
                    />
                </mesh>
            ))}
        </group>
    );
};

export default MotionBlobs;
