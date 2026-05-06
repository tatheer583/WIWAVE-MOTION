import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * High-frequency noise particles that react to jitter.
 */
const MicroMotionBubbles = ({ jitter }) => {
    const groupRef = useRef();
    
    const count = 30;
    const particles = useMemo(() => {
        return Array.from({ length: count }, () => ({
            position: [(Math.random() - 0.5) * 10, Math.random() * 5, (Math.random() - 0.5) * 10],
            speed: 0.1 + Math.random() * 0.2,
            factor: 2 + Math.random() * 4
        }));
    }, []);

    useFrame((state) => {
        if (!groupRef.current) return;
        const time = state.clock.getElapsedTime();
        
        // Intensity of bubble movement scales with jitter
        const intensity = Math.min(1.0, jitter * 0.5);
        
        groupRef.current.children.forEach((child, i) => {
            const p = particles[i];
            
            // Floating motion + Jitter reaction
            child.position.y = p.position[1] + Math.sin(time * p.speed) * 0.5;
            child.position.x = p.position[0] + Math.cos(time * p.speed + p.factor) * intensity;
            child.position.z = p.position[2] + Math.sin(time * p.speed + p.factor) * intensity;
            
            // Opacity based on overall jitter
            child.material.opacity = THREE.MathUtils.lerp(child.material.opacity, intensity * 0.4, 0.1);
        });
    });

    return (
        <group ref={groupRef}>
            {particles.map((p, i) => (
                <mesh key={i} position={p.position}>
                    <sphereGeometry args={[0.1, 8, 8]} />
                    <meshBasicMaterial color="#00ffcc" transparent opacity={0} blending={THREE.AdditiveBlending} />
                </mesh>
            ))}
        </group>
    );
};

export default MicroMotionBubbles;
