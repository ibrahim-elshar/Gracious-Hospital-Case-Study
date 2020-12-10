#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import simpy
import numpy as np
import matplotlib.pyplot as plt
                
class Hospital_simulation(object):
     def __init__(self, env,reorder_pt, order_target):
         self.env = env
         # start initial inventory from the order-upto-levels
         self.inventory = order_target.copy()
         self.num_ordered = np.array([0,0])
         self.patient = 0
         self.reorder_pt = reorder_pt
         self.order_target = order_target
         self.patient_status = [0,0]
         self.demand = np.array([0,0])
         # Start the run process everytime an instance is created.
         self.action = self.env.process(self.serve_patient())
         self.observe_run =self.env.process(self.observe())
         self.flag =0

         self.obs_time = []
         self.inventory_level = []
         self.next_delivery=np.array([float('inf'),float('inf')])
         self.tech_visits_cent = 0
         # track the number of patients not served by ADC
         self.patient_not_serv_by_ADC = 0
         
     def serve_patient(self,):
         ''' Run simulation'''
         while True:
             nur_flag = 0
             phy_flag = 0
             # Find the patients that are not seen by the physician yet
             k =[i for i,j in enumerate(self.patient_status) if j==0]
             print('Start simulation at %f' % self.env.now)
             print('inventory',self.inventory)
             if len(k)>0:
                 m=k[0]
                 phy= self.env.process(self.physician_event(m))
                 phy_flag = 1
                 print( 'patient_status=', self.patient_status,'at',env.now)
             # Find the patients that are not seen by the nurse yet
             l =[i for i,j in enumerate(self.patient_status) if j==1]
             if len(l)>0:
                 m=l[0]
                 nur=self.env.process(self.nurse(m))
                 nur_flag = 1
                 print( 'patient_status=', self.patient_status, 'at', env.now)
             if  phy_flag & nur_flag:  
                 print('Entered phy_flag & nur_flag')
                 yield phy & nur
             elif phy_flag:
                 print('Entered phy')
                 yield phy
             elif nur_flag:
                 print('Entered nur')
                 yield nur
                 
     def observe(self):
         ''' Keeps track of the I.L in 0.1 time intervals '''
         while True:
            self.obs_time.append(self.env.now)
            self.inventory_level.append(self.inventory.copy())
            yield self.env.timeout(0.1)
        
         
         
     def physician(self):
        ''' 
        Listens to the patient and writes a "prescription" corresponding 
        to patient's "demand".
        '''
        self.demand = self.generate_prescription()
        return np.random.uniform(5/60, 15/60)
    
     def physician_event(self,m):
         self.patient += 1
         duration = self.physician()
         print('phys time',duration, 'happens at', self.env.now + duration)
         yield  self.env.timeout(duration)
         # Changes the status of a patient to seen by the Dr.
         self.patient_status[m]=1
         print( 'patient_status=', self.patient_status,'at', self.env.now) 
         
         
     def generate_prescription(self):
        ''' Generates the demand for each drug'''
        return np.array([np.random.randint(1,6+1),
                         round(4*np.random.beta(6,2))])         

     def nurse(self, k):
        '''
        Receives "prescription" from physician
        Checks automated dispensing cabinet (ADC) to fill prescription
        Delivers "medication" to patient
        '''
        nurse_time = self.nurse_deliver_medication() 
        print('nurse time',nurse_time,'happens at', self.env.now + nurse_time)
        print('self.demand:',self.demand)
        yield self.env.timeout(nurse_time)
        
        flag = 0
        for i in range(2):
            if self.inventory[i] >= self.demand[i]:
                self.inventory[i] -= self.demand[i]
                flag += 1
            else:
                self.inventory[i] = 0
   
        if flag < 2:
            # if the ADC I.L is not enough to satisfy demand
            self.patient_not_serv_by_ADC += 1
            print("flag < 2 at:", self.env.now)
            if min(self.patient_status) <=1:
                # change the status of the patient to seen by nurse
                # and waiting fot central pharmacy delivery
                self.patient_status[k] = 2
                print('patient_status',self.patient_status, 
                      'at:',self.env.now)
                # send technician to the central pharmacy
                self.env.process(self.handle_ADC_restock(k))
                if min(self.patient_status) >1:
                    # if both patient are waiting 
                    # the central pharmacy delivery
                    print('pateint_status for both patients is 2')
                    print('env.now:',self.env.now)
                    print('Next delivery time:',min(self.next_delivery))
                    # need to yield the next delivery event
                    # since both patients are waiting fot C.Ph delivery
                    yield self.env.timeout(min(self.next_delivery)-self.env.now)
                    print('After yield (i.e., next delivery event)')
                    self.patient_status = np.array([1,1])
                    print('patient_status',self.patient_status,
                          'at:',self.env.now)
        else:
            # demand can be satisfied from ADC
            # change the patient status to can be seen by the Physician
            # equivalent to receiving a new patient
            self.patient_status[k] = 0
            print('patient_status',self.patient_status, 'at:',self.env.now)
            # check if the ADC I.L is below the reorder pts
            # if yes reorders
            self.env.process(self.handle_ADC_restock(k))
        print('self.patient_status',self.patient_status, 'at:',self.env.now)   
            
    
     def nurse_deliver_medication(self):
        ''' Generate the time the nure needs to order/give medication'''
        return np.random.uniform(1/60,5/60)   

            
     def handle_ADC_restock(self,kl):
        '''
        Physician technician 
        Fills requests from the nurse if there is a “stockout”
        Takes order to Central Pharmacy and waits for it to be filled
        Delivers order to ADC
        Responsible for periodically monitoring the quantity of “drug” 
        in the ADC and replenishing the ADC according to the restocking policy
        '''
        print('Physician technician is called to refill ADC')
        idx = [0,0]
        for i in range(2):
            if self.inventory[i] < self.reorder_pt[i] and\
                self.num_ordered[i]== 0: 
               idx[i]=1
               self.num_ordered[i] = self.order_target[i] - self.inventory[i]
        # if the IL is below reorder points and there is no ongoing orders
        if max(idx)==1:
            # increment the technician visits to the central pharmacy
            self.tech_visits_cent +=1
            k =[i for i,j in enumerate(idx) if j==1]
            # generate the time for the technician 
            var = np.random.uniform(40/60, 90/60) 
            # store next delivery arrival time
            self.next_delivery[k]=var + self.env.now
            print('techinician time:',var, 'restock happens at', 
                  self.env.now + var,"inventory=",self.inventory)
            yield self.env.timeout(var)
            # add the number ordered to the IL
            self.inventory[k] += self.num_ordered[k]
            # set back the number ordered to zero
            self.num_ordered[k]=0
            self.next_delivery[k]=float('inf')
            print('restock happened at',self.env.now,
                  "inventory=",self.inventory)
            # change patient status back to can be seen by the nurse 
            # so it can give the patient the medication
            if self.patient_status[kl]==2:
                self.patient_status[kl]=1

num_rep=100
num_patient_served =[]
num_tech_cent =[]
avg_il0 = []
avg_il1 = []
ill0 = np.zeros((100,121))
ill1 = np.zeros((100,121))
patient_not_serv_by_ADC =[]
for _ in range(num_rep):
    np.random.seed(_)
    env = simpy.Environment()
    s = Hospital_simulation(env, np.array([55,50]),np.array([75,70]))
    env.run(until=12)   
    num_patient_served.append(s.patient)
    num_tech_cent.append(s.tech_visits_cent)
    il0=np.array([i[0] for i in s.inventory_level])
    il1=np.array([i[1] for i in s.inventory_level])
    ill0[_,:]=il0 
    ill1[_,:]=il1 
    area_il0 = il0*0.1
    area_il1 = il1*0.1
    avg_il0.append(sum(area_il0)/12.0)
    avg_il1.append(sum(area_il1)/12.0)
    patient_not_serv_by_ADC.append(s.patient-s.patient_not_serv_by_ADC)
    
print('avg num patient served:', np.mean(num_patient_served))
print('std num patient served:', np.std(num_patient_served))  
print('avg num tech cent:', np.mean(num_tech_cent))
print('std num tech cent:', np.std(num_tech_cent))  
print('avg ilA:', np.mean(avg_il0))
print('std ilA:', np.std(avg_il0))   
print('avg ilB:', np.mean(avg_il1))
print('std ilB:', np.std(avg_il1))
print('avg num patient served by ADC:', np.mean(patient_not_serv_by_ADC))
print('std num patient served by ADC:', np.std(patient_not_serv_by_ADC))  
plt.hist(num_patient_served, bins='auto')
plt.xlabel('No. of patients served', fontsize=15)
plt.show()
plt.plot(s.obs_time, np.mean(ill0,axis=0),label='A')
plt.plot(s.obs_time, np.mean(ill1,axis=0),label='B')
plt.xlabel('Simulation time (hrs)', fontsize=15)
plt.ylabel('Inventory level', fontsize=15) 
plt.legend()
plt.show()