import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * Renders glowing blobs/particles when motion is detected.
 */
const MotionBlobs = ({ motionDetected, variance }) => {
    const groupRef = useRef();
    
    // Create a set of random positions for the blobs
    const blobData = useMemo(() => {
        return Array.from({ length: 15 }, () => ({
            position: [
                (Math.random() - 0.5) * 15,
                Math.random() * 5,
                (Math.random() - 0.5) * 15
            ],
            speed: 0.5 + Math.random(),
            offset: Math.random() * Math.PI * 2,
            scale: 0.2 + Math.random() * 0.8
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
