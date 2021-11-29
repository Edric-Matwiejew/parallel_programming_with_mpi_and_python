from mpi4py import MPI
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

# number of processes in the MPI communicator
size=MPI.COMM_WORLD.size
# ID of each process in the MPI communicator
rank=MPI.COMM_WORLD.rank
# number of rows and columns in the game of life grid
num_points=60
# ?
sendbuf=[]
# 'root' process collects the final result of each iteration
root=0

from numpy import r_
#j=np.complex(0,1)
# the number of rows at each rank
rows_per_process=int(num_points/size)

# number of game iterations 
num_iter=0
# maximum number of iterations
max_iter=100

# 'alive' cells in the game
current_population=1
# 'alive' cell at each rank   
population_list = np.empty(size, dtype = np.float64)
# stop when there are no 'alive' cells
stop_population = 0

def numpyTimeStep(u):

    kernel = np.ones((3,3), dtype = float)
    kernel[1,1] = 0


    m = u.shape[0]
    n = u.shape[1]

    u_old = u.copy()

    neighbours = signal.convolve(u, kernel, mode='same')
    
    for i in range(m):
        for j in range(n):
            if u_old[i,j] == 1:
                if neighbours[i,j] < 2:
                    u[i,j] = 0
                elif neighbours[i,j] > 3:
                    u[i,j] = 0
            else:
                if neighbours[i,j] == 3:
                    u[i,j] = 1

    return u, u.sum()


if rank==0:

    # populate initial array
    #m=np.zeros((num_points,num_points),dtype=float)
    m = np.random.choice(np.array([0,1], dtype = float), size=(num_points,num_points), p = [0.7,0.3])

    # game paritions to send
    l=np.array([ m[i*rows_per_process:(i+1)*rows_per_process,:] for i in range(size)])
    sendbuf=l

# local game game partitions
my_grid = np.empty((rows_per_process, num_points), dtype = np.float64)

# Scatter the game partitions 
MPI.COMM_WORLD.Scatter(
        [sendbuf, MPI.DOUBLE],
        [my_grid, MPI.DOUBLE],
        root = 0)

# for all ranks except rank '0' (the 'top') create an array
# for recieval of the boarder-values from the 'above' rank.
if rank > 0:
    row_above = np.empty((1, num_points), dtype = np.float64)
# for all ranks except rank 'size - 1' create an array
# for the recieval of the boarder-values from the 'below' rank.
if rank < size - 1:
    row_below = np.empty((1, num_points), dtype = np.float64)


# tags
# row_above: rank of sender * 2
# row_below: rank of sender * 2 + 1

current_population = np.inf
while num_iter <  max_iter:

    if current_population < stop_population:
        break

    # non-blocking send from rank 0 to 
    # rank 1.
    if rank == 0:


        MPI.COMM_WORLD.Isend(
                [my_grid[-1,:], MPI.DOUBLE],
                dest = 1,
                tag = rank * 2)

    
    # non-blocking send to the 'below'
    # rank and receive from the 'above' rank
    if rank > 0 and rank< size-1:

        MPI.COMM_WORLD.Irecv(
                [row_above, MPI.DOUBLE],
                source = rank - 1,
                tag = (rank - 1) * 2)

        MPI.COMM_WORLD.Isend(
                [my_grid[-1,:], MPI.DOUBLE],
                dest = rank + 1,
                tag = rank * 2)

    # non-blocking receive from the 'above'
    # rank and send to the 'above' rank
    if rank==size-1:

        MPI.COMM_WORLD.Irecv(
                [row_above, MPI.DOUBLE],
                source = rank - 1,
                tag = (rank - 1)* 2)

        MPI.COMM_WORLD.Isend(
                [my_grid[0,:], MPI.DOUBLE],
                dest = rank - 1,
                tag = rank * 2 + 1)

    # non-blocking receive from the 'below'
    # rank and send to the 'above' rank
    if rank > 0 and rank< size-1:

        MPI.COMM_WORLD.Irecv(
                [row_below, MPI.DOUBLE],
                source = rank + 1,
                tag = (rank + 1) * 2 + 1)

        MPI.COMM_WORLD.Isend(
                [my_grid[0,:], MPI.DOUBLE],
                dest = rank - 1,
                tag = rank * 2 + 1)

    # non-block receive from the 'below' rank
    if rank==0:

        MPI.COMM_WORLD.Irecv(
                [row_below, MPI.DOUBLE],
                source = 1,
                tag = 3)


    # ensure all of the non-blocking pairs have completed
    # to avoid race-conditions in the next section.
    MPI.COMM_WORLD.Barrier()

    if rank >0 and rank < size-1:

        row_below.shape=(1,num_points)
        row_above.shape=(1,num_points)

        # calculate the next game iteration and the number of
        # 'alive' cells in the next interation.
        u,err =numpyTimeStep(r_[row_above,my_grid,row_below])

        my_grid=u[1:-1,:]


    if rank==0:

        row_below.shape=(1,num_points)

        # calculate the next game iteration and the number of
        # 'alive' cells in the next interation.
        u,err=numpyTimeStep(r_[my_grid,row_below])

        my_grid=u[0:-1,:]


    #print(rank, flush = True)
    if rank==size-1:

        row_above.shape=(1,num_points)

        # calculate the next game iteration and the number of
        # 'alive' cells in the next interation.
        u,err=numpyTimeStep(r_[row_above,my_grid])

        my_grid=u[1:,:]


    # gather the game partitions to the root process
    MPI.COMM_WORLD.Gather(
            [err, MPI.DOUBLE],
            [population_list, MPI.DOUBLE],
            root)

    # at the roor process calculate the total number of 'alive' cells
    if rank==0:
        current_population = 0
        for a in population_list:
            current_population += a
        print("iterations: %i"%num_iter, "alive cells: %f"%current_population, flush= True)

    # send the total number of 'alive' cells to each MPI rank
    current_population = MPI.COMM_WORLD.bcast(
            current_population,
            root)



    # 'python' version of the gather directive
    # game partitions are gathered in a python list
    recvbuf=MPI.COMM_WORLD.gather(my_grid,root)
    
    if rank==0:
        sol=np.array(recvbuf)
        sol=sol.reshape([num_points,num_points])
        plt.matshow(sol)
        plt.savefig(f"results/game_state_{num_iter}")

    # increment the total number of game iterations.
    num_iter=num_iter+1
    # ensure the next loop is synchronised
    MPI.COMM_WORLD.Barrier()

MPI.COMM_WORLD.Barrier()
