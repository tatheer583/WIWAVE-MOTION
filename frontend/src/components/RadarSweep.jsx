import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * A rotating radar sweep beam.
 */
const RadarSweep = () => {
    const sweepRef = useRef();

    useFrame((state) => {
        if (!sweepRef.current) return;
        sweepRef.current.rotation.y += 0.03;
    });

    return (
        <group ref={sweepRef}>
            {/* The sweep beam - a semi-transparent wedge */}
            <mesh rotation={[0, 0, 0]} position={[0, 0, 0]}>
                <coneGeometry args={[10, 0, 32, 1, true, 0, Math.PI / 4]} />
                <meshBasicMaterial 
                    color="#00ffcc" 
                    transparent 
                    opacity={0.1} 
                    side={THREE.DoubleSide} 
                    blending={THREE.AdditiveBlending}
                />
            </mesh>
            
            {/* A thin bright edge for the sweep */}
            <mesh rotation={[0, 0, 0]}>
                <boxGeometry args={[10, 0.05, 0.05]} />
                <meshBasicMaterial color="#00ffcc" />
            </mesh>
        </group>
    );
};

export default RadarSweep;
