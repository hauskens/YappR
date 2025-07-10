interface BalloonButton extends HTMLElement {
    dataset: {
        clipId: string;
        userId: string;
        feedbackType: string;
    };
}

class BalloonFeedback {
    private buttons: NodeListOf<BalloonButton>;
    private isHolding: boolean = false;
    private holdTimer: NodeJS.Timeout | null = null;
    private currentPower: number = 0.2;
    private readonly maxPower: number = 1.0;
    private readonly minPower: number = 0.2;
    private holdDuration: number = 0;
    private readonly inflationRate: number = 50; // milliseconds between power increases

    constructor() {
        this.buttons = document.querySelectorAll('.balloon-btn') as NodeListOf<BalloonButton>;
        this.init();
    }

    private init(): void {
        this.buttons.forEach(button => {
            // Mouse events
            button.addEventListener('mousedown', (e) => this.startHold(e, button));
            button.addEventListener('mouseup', (e) => this.endHold(e, button));
            button.addEventListener('mouseleave', (e) => this.endHold(e, button));
            
            // Touch events for mobile
            button.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.startHold(e, button);
            });
            button.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.endHold(e, button);
            });
            button.addEventListener('touchcancel', (e) => {
                e.preventDefault();
                this.endHold(e, button);
            });
        });
        
        // Prevent context menu on long press
        document.addEventListener('contextmenu', (e) => {
            if ((e.target as HTMLElement).closest('.balloon-btn')) {
                e.preventDefault();
            }
        });
    }

    private startHold(event: Event, button: BalloonButton): void {
        if (this.isHolding) return;
        
        this.isHolding = true;
        this.currentPower = this.minPower;
        this.holdDuration = 0;
        
        // Start inflation animation
        button.classList.add('inflating');
        this.updateBalloonSize(button, this.currentPower);
        
        // Start the inflation timer
        this.holdTimer = setInterval(() => {
            this.holdDuration += this.inflationRate;
            
            // Increase power exponentially for satisfying balloon feel
            const progress = Math.min(this.holdDuration / 2000, 1); // 2 seconds to max
            this.currentPower = this.minPower + (this.maxPower - this.minPower) * this.easeOutQuad(progress);
            
            this.updateBalloonSize(button, this.currentPower);
            this.updatePowerIndicator(button, this.currentPower);
            
            if (this.currentPower >= this.maxPower) {
                clearInterval(this.holdTimer!);
            }
        }, this.inflationRate);
    }

    private endHold(event: Event, button: BalloonButton): void {
        if (!this.isHolding) return;
        
        this.isHolding = false;
        if (this.holdTimer) {
            clearInterval(this.holdTimer);
        }
        
        // Stop inflation animation
        button.classList.remove('inflating');
        
        // Trigger pop effect
        this.triggerPop(button, this.currentPower);
        
        // Send feedback
        this.sendFeedback(button, this.currentPower);
        
        // Reset button
        setTimeout(() => {
            this.resetButton(button);
        }, 600);
    }

    private updateBalloonSize(button: BalloonButton, power: number): void {
        const scale = 1 + (power / this.maxPower) * 0.5; // Scale up to 1.5x
        const pressureSize = (power / this.maxPower) * 100; // Pressure indicator size
        
        button.style.setProperty('--balloon-scale', scale.toString());
        button.style.setProperty('--pressure-size', pressureSize + 'px');
    }

    private updatePowerIndicator(button: BalloonButton, power: number): void {
        const powerValue = button.querySelector('.power-value') as HTMLElement;
        const isGood = button.classList.contains('good');
        const sign = isGood ? '+' : '-';
        powerValue.textContent = power.toFixed(1);
        
        // Change color intensity based on power
        const intensity = power / this.maxPower;
        button.style.filter = `brightness(${1 + intensity * 0.5})`;
    }

    private triggerPop(button: BalloonButton, power: number): void {
        const scale = 1 + (power / this.maxPower) * 0.5;
        button.style.setProperty('--final-scale', scale.toString());
        button.classList.add('popping');
        
        // Create particle burst
        this.createParticles(button, power);
        
        setTimeout(() => {
            button.classList.remove('popping');
        }, 600);
    }

    private createParticles(button: BalloonButton, power: number): void {
        const particleCount = Math.floor(power * 8); // More particles for higher power
        const rect = button.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle burst';
            
            // Random direction and distance
            const angle = (i / particleCount) * Math.PI * 2;
            const distance = 30 + power * 50;
            const x = Math.cos(angle) * distance;
            const y = Math.sin(angle) * distance;
            
            particle.style.setProperty('--particle-x', x + 'px');
            particle.style.setProperty('--particle-y', y + 'px');
            particle.style.left = centerX + 'px';
            particle.style.top = centerY + 'px';
            particle.style.color = getComputedStyle(button).color;
            
            document.body.appendChild(particle);
            
            // Remove particle after animation
            setTimeout(() => particle.remove(), 600);
        }
    }

    private sendFeedback(button: BalloonButton, power: number): void {
        const clipId = button.dataset.clipId;
        const userId = button.dataset.userId;
        const feedbackType = button.dataset.feedbackType;
        const isGood = feedbackType === 'good';
        const adjustment = isGood ? power : -power;
        
        // Show weight change display
        this.showWeightChange(adjustment);
        
        // Update current weight display
        this.updateCurrentWeight(adjustment);
        
        // HTMX request to backend
        // htmx.ajax('POST', '/gamification/balloon_feedback', {
        //     values: {
        //         clip_id: clipId,
        //         user_id: userId,
        //         adjustment: adjustment.toFixed(2),
        //         feedback_type: feedbackType
        //     }
        // }).then(() => {
        //     console.log('Feedback sent successfully');
        // }).catch((error) => {
        //     console.error('Failed to send feedback:', error);
        // });
    }

    private showWeightChange(adjustment: number): void {
        const display = document.getElementById('weight-change-display');
        if (!display) return;
        
        const text = document.getElementById('weight-change-text');
        if (!text) return;
        
        const sign = adjustment > 0 ? '+' : '';
        
        text.textContent = `${sign}${adjustment.toFixed(1)} Weight!`;
        display.style.color = adjustment > 0 ? '#28a745' : '#dc3545';
        display.classList.add('show');
        
        setTimeout(() => {
            display.classList.remove('show');
        }, 2000);
    }

    private updateCurrentWeight(adjustment: number): void {
        const weightElement = document.getElementById('current-weight');
        if (!weightElement) return;
        
        const currentWeight = parseFloat(weightElement.textContent || '0');
        const newWeight = Math.max(0.1, Math.min(3.0, currentWeight + adjustment));
        
        weightElement.textContent = newWeight.toFixed(1);
        weightElement.style.color = adjustment > 0 ? '#28a745' : '#dc3545';
        
        setTimeout(() => {
            weightElement.style.color = '';
        }, 1000);
    }

    private resetButton(button: BalloonButton): void {
        button.style.removeProperty('--balloon-scale');
        button.style.removeProperty('--pressure-size');
        button.style.removeProperty('--final-scale');
        button.style.filter = '';
        this.updatePowerIndicator(button, this.minPower);
    }

    // Easing function for smooth balloon inflation
    private easeOutQuad(t: number): number {
        return t * (2 - t);
    }

    // Reinitialize for dynamically added buttons
    public reinitialize(): void {
        this.buttons = document.querySelectorAll('.balloon-btn') as NodeListOf<BalloonButton>;
        this.init();
    }
}

// Initialize balloon feedback system
function initializeBalloonFeedback(): void {
    if ((window as any).balloonFeedback) {
        (window as any).balloonFeedback.reinitialize();
    } else {
        (window as any).balloonFeedback = new BalloonFeedback();
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', initializeBalloonFeedback);

// Add some haptic feedback for mobile devices
function triggerHaptic(): void {
    if (navigator.vibrate) {
        navigator.vibrate(10);
    }
}